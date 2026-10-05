"""Official shared app-server transport; no private session files or extra daemon."""
import base64
import hashlib
import json
import os
import queue
import threading
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import time


class ProxyStream:
    """Raw byte relay through the official CLI, not a new app-server process.

    CPython on native Windows has no AF_UNIX. The official proxy owns the
    platform-specific UDS connection; this client still performs WebSocket.
    Reader/writer threads make pipe I/O timeouts work on Windows without select.
    """
    def __init__(self, codex, endpoint, timeout=15):
        self.timeout = timeout
        self.pending = bytearray()
        self.incoming = queue.Queue(maxsize=256)
        self.closed = threading.Event()
        self.process = subprocess.Popen(
            [str(codex), 'app-server', 'proxy', '--sock', str(endpoint)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while not self.closed.is_set():
                part = self.process.stdout.read(65536)
                while not self.closed.is_set():
                    try:
                        self.incoming.put(part, timeout=0.1)
                        break
                    except queue.Full:
                        pass
                if not part:
                    return
        except (OSError, ValueError):
            if not self.closed.is_set():
                try:
                    self.incoming.put_nowait(b'')
                except queue.Full:
                    pass

    def settimeout(self, timeout):
        self.timeout = timeout

    def recv(self, count):
        if not self.pending:
            try:
                self.pending.extend(self.incoming.get(timeout=self.timeout))
            except queue.Empty:
                raise TimeoutError('Official app-server proxy timed out; verify the running shared daemon and CLI proxy support. WSL2 is an alternative when all components run in the same Linux distribution.') from None
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def sendall(self, data):
        done = queue.Queue(maxsize=1)
        def write():
            try:
                remaining = memoryview(data)
                while remaining:
                    count = self.process.stdin.write(remaining)
                    if not count:
                        raise BrokenPipeError('Official app-server proxy closed its input')
                    remaining = remaining[count:]
                done.put(None)
            except (OSError, ValueError) as error:
                done.put(error)
        threading.Thread(target=write, daemon=True).start()
        try:
            error = done.get(timeout=self.timeout)
        except queue.Empty:
            self.close()
            raise TimeoutError('Official app-server proxy write timed out') from None
        if error is not None:
            raise RuntimeError('Official app-server proxy unavailable; verify CLI proxy support and the existing daemon') from error

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        # Only this byte-relay child is stopped; never the shared daemon.
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        for handle in (self.process.stdin, self.process.stdout):
            handle.close()
        self.reader.join(timeout=2)


class TurnFailed(RuntimeError):
    pass

class RequestRejected(RuntimeError):
    pass

class AppServer:
    def __init__(self, endpoint, timeout=15, *, codex='codex'):
        if not isinstance(endpoint, (str, Path)) or not str(endpoint).strip():
            raise ValueError('An existing official app-server socket path is required')
        if '://' in str(endpoint) or str(endpoint).startswith('\\\\.\\pipe\\'):
            raise ValueError('Expected a local socket path, not a URL or named pipe')
        self.timeout = timeout
        if os.name == 'nt':
            self.socket = ProxyStream(codex, endpoint, timeout)
        else:
            if not hasattr(socket, 'AF_UNIX'):
                raise RuntimeError('Python AF_UNIX is unavailable; run Codex, Python and this project together in WSL2')
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                self.socket.settimeout(timeout)
                self.socket.connect(str(endpoint))
            except BaseException:
                self.socket.close()
                raise
        self.sequence = 0
        try:
            self._initialize()
        except BaseException:
            self.socket.close()
            raise

    def _initialize(self):
        key=base64.b64encode(secrets.token_bytes(16)).decode()
        self.socket.sendall(('GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: '+key+'\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        raw=b''
        while not raw.endswith(b'\r\n\r\n'):
            if len(raw)>8192:raise RuntimeError('Oversized transport header')
            raw+=self.exact(1)
        lines=raw.decode().split('\r\n');headers={k.lower():v.strip() for k,v in (line.split(':',1) for line in lines[1:] if ':' in line)}
        expected=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        if ' 101 ' not in lines[0] or headers.get('sec-websocket-accept')!=expected:raise RuntimeError('Official WebSocket handshake failed')
        self.request('initialize',{'clientInfo':{'name':'project_delegation','version':'2.0'},'capabilities':{'experimentalApi':True}})
        self.send({'method':'initialized'})

    def exact(self,n):
        data=b''
        while len(data)<n:
            part=self.socket.recv(n-len(data))
            if not part:raise RuntimeError('Official app-server disconnected')
            data+=part
        return data

    def frame(self,payload,opcode=1):
        mask=secrets.token_bytes(4);n=len(payload)
        size=bytes([128|n]) if n<126 else (bytes([254])+struct.pack('!H',n) if n<65536 else bytes([255])+struct.pack('!Q',n))
        self.socket.sendall(bytes([128|opcode])+size+mask+bytes(v^mask[i%4] for i,v in enumerate(payload)))

    def send(self,value):self.frame(json.dumps(value).encode())

    def receive(self):
        data=bytearray();started=False
        while True:
            first,second=self.exact(2);opcode=first&15;n=second&127
            if n==126:n=struct.unpack('!H',self.exact(2))[0]
            elif n==127:n=struct.unpack('!Q',self.exact(8))[0]
            if second&128 or n+len(data)>16*1024*1024:raise RuntimeError('Invalid/oversized frame')
            payload=self.exact(n)
            if opcode==8:raise RuntimeError('Official app-server closed connection')
            if opcode==9:self.frame(payload,10);continue
            if opcode==10:continue
            if (opcode==1 and started) or (opcode==0 and not started) or opcode not in (0,1):raise RuntimeError('Invalid frame sequence')
            started=True;data.extend(payload)
            if first&128:return json.loads(data)

    def request(self,method,params):
        self.sequence+=1;request_id=self.sequence
        self.send({'id':request_id,'method':method,'params':params})
        deadline=time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            value=self.receive()
            if value.get('id')==request_id:
                if 'error' in value:raise RequestRejected('Official request failed: '+str(value['error'].get('message','unknown')))
                return value['result']
        raise TimeoutError('Official request timed out')

    def thread(self,thread_id,workspace,turns=False):
        value=self.request('thread/read',{'threadId':thread_id,'includeTurns':turns})['thread']
        if value.get('id')!=thread_id or Path(value.get('cwd','')).resolve()!=Path(workspace).resolve():raise ValueError('Official thread identity/workspace mismatch')
        if value.get('status',{}).get('type') not in ('active','idle'):raise RuntimeError('Target is not loaded in this app-server; no replacement instance will be created')
        return value

    def close(self):self.socket.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()


def endpoint(codex):
    result=subprocess.run([codex,'app-server','daemon','version'],capture_output=True,text=True,encoding='utf-8',timeout=15)
    if result.returncode:raise RuntimeError('Existing official app-server unavailable')
    value=json.loads(result.stdout)
    if not isinstance(value, dict) or value.get('status')!='running' or not isinstance(value.get('socketPath'), str) or not value['socketPath'].strip():raise RuntimeError('No running shared app-server')
    return value['socketPath']


def turn_result(thread, request_text):
    matches=[]
    for turn in thread.get('turns',[]):
        users=[i for i in turn.get('items',[]) if i.get('type')=='userMessage']
        if any(any(c.get('type')=='text' and c.get('text')==request_text for c in item.get('content',[])) for item in users):matches.append(turn)
    if len(matches)>1:raise RuntimeError('Duplicate queue request turns; reconcile before continuing')
    if not matches:return None
    turn=matches[0]
    if turn.get('status') in ('failed','interrupted'):raise TurnFailed('Queued coordinator turn ended '+turn['status'])
    if turn.get('status')!='completed':return None
    messages=[i.get('text','') for i in turn.get('items',[]) if i.get('type')=='agentMessage' and i.get('phase')!='commentary']
    if not messages:raise TurnFailed('Completed coordinator turn has no final response')
    return '\n'.join(messages)
