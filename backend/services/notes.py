"""Research notes and their run references."""
from backend.api.schemas import NoteRequest
from backend.services.errors import ResearchError
from backend.services.research import ResearchService


class NoteService:
    def __init__(self, research: ResearchService):
        self.research = research
        self.store = research.store

    def list_notes(self, run_id: str | None = None):
        return {"notes": self.store.list_notes(run_id)}

    def create_note(self, note: NoteRequest):
        if note.run_id:
            self.research.require_run(note.run_id)
        return self.store.save_note(note.title, note.body, note.run_id)

    def update_note(self, identifier: str, note: NoteRequest):
        if not any(item["id"] == identifier for item in self.store.list_notes()):
            raise ResearchError(404, "笔记不存在")
        if note.run_id:
            self.research.require_run(note.run_id)
        return self.store.save_note(note.title, note.body, note.run_id, identifier)

    def run_note(self, identifier: str, note: NoteRequest):
        self.research.require_run(identifier)
        notes = self.store.list_notes(identifier)
        return self.store.save_note(note.title, note.body, identifier, notes[0]["id"] if notes else None)

    def delete_note(self, identifier: str):
        if not self.store.delete_note(identifier):
            raise ResearchError(404, "笔记不存在")
        return {"deleted": True}
