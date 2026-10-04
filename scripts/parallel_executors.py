#!/usr/bin/env python3
"""Bounded independent executor slots with file/resource leases."""
import threading
from pathlib import PurePosixPath


def overlaps(a,b):
    a=PurePosixPath(a);b=PurePosixPath(b)
    return a==b or a in b.parents or b in a.parents


class ScopeGate:
    def __init__(self):
        self.condition=threading.Condition();self.owners={}
    def available(self,paths,resources=()):
        resources=set(resources)
        with self.condition:return all(not(resources & value['resources']) and not any(overlaps(a,b) for a in paths for b in value['paths']) for value in self.owners.values())
    def try_acquire(self,key,paths,resources=()):
        with self.condition:
            if not self.available(paths,resources):return False
            self.owners[key]={'paths':list(paths),'resources':set(resources)};return True
    def acquire(self,key,paths,resources=()):
        resources=set(resources)
        with self.condition:
            self.condition.wait_for(lambda:all(not(resources & value['resources']) and not any(overlaps(a,b) for a in paths for b in value['paths']) for value in self.owners.values()))
            self.owners[key]={'paths':list(paths),'resources':resources}
    def release(self,key):
        with self.condition:self.owners.pop(key,None);self.condition.notify_all()
