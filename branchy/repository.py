from dataclasses import dataclass
from gi.repository import Gtk


@dataclass
class Branch:
    name: str
    timestamp: int
    packages: list[str]
    version: str
    radio: Gtk.CheckButton = None


class Repository:
    def __init__(self, name: str):
        self.name = name
        self.branches: list[Branch] = []

    def add_branch(self, branch: Branch):
        self.branches.append(branch)
        self.branches.sort(key=lambda x: x.timestamp, reverse=True)
