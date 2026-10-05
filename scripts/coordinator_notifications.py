"""One conservative queue-delivery protocol for fixed-coordinator notices.

The caller owns durable storage and binding checks. Queue acknowledgement is
delivery evidence, never evidence that the coordinator reviewed or accepted work.
"""
import time

from app_server_client import RequestRejected, TurnFailed, turn_result


PENDING = {'prepared', 'submitting', 'queued'}


def pending_notice(entry):
    return entry['status'] in PENDING or (entry['status'] == 'delivered'
        and entry.get('turn_status') not in {'completed', 'failed', 'interrupted'})


def reconcile_notice(client, identity, workspace, entry, save):
    thread = client.thread(identity, workspace, turns=True)
    turn_error = None
    try:
        turn_result(thread, entry['text'])
    except TurnFailed as exc:
        turn_error = str(exc)
    matches = [turn for turn in thread.get('turns', []) if any(
        item.get('type') == 'userMessage' and any(
            c.get('type') == 'text' and c.get('text') == entry['text']
            for c in item.get('content', [])) for item in turn.get('items', []))]
    if matches:
        entry.update(status='delivered', turn_id=matches[0].get('id'),
                     turn_status=matches[0].get('status', 'unknown'), reconciled_at=time.time())
        if turn_error:
            entry['turn_error'] = turn_error
        else:
            entry.pop('turn_error', None)
        save()


def deliver_notice(client, identity, workspace, entry, save, assert_binding):
    if not pending_notice(entry):
        return
    assert_binding()
    if entry['status'] != 'prepared':
        reconcile_notice(client, identity, workspace, entry, save)
        return  # Missing history cannot prove an uncertain submission was unsent.
    client.thread(identity, workspace)  # Busy coordinators receive queued input.
    assert_binding()
    entry.update(status='submitting', attempted_at=time.time())
    save()  # A crash after this point requires reconciliation, not resubmission.
    if entry['status'] != 'submitting':
        return  # Storage may retire a definitely-unsent obsolete event atomically.
    try:
        result = client.request('thread/queue/add', {
            'threadId': identity, 'clientUserMessageId': entry['id'],
            'input': [{'type': 'text', 'text': entry['text'], 'text_elements': []}]})
    except RequestRejected as exc:
        entry.update(status='rejected', error=str(exc))
        save()
        return
    except Exception as exc:
        entry['error'] = 'Uncertain delivery: ' + str(exc)
        save()
        raise
    queue_id = result.get('queuedSubmission', {}).get('id')
    if not queue_id:
        entry['error'] = 'Missing queue receipt; delivery remains uncertain'
        save()
        raise RuntimeError(entry['error'])
    entry.update(status='queued', queue_id=queue_id, queued_at=time.time())
    entry.pop('error', None)
    save()
