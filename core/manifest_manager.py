import os
import json
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional

@dataclass
class PilotInfo:
    id: str
    nome: str
    vela_marca_modello: str = ""
    colori_vela: str = ""
    imbrago: str = ""
    livello: str = ""
    note: str = ""
    cartella: str = ""

    def __post_init__(self):
        if not self.cartella:
            safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in self.nome)
            self.cartella = safe_name.strip("_") or "Pilota"
        if not self.id:
            self.id = self.cartella.lower()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'PilotInfo':
        return cls(**data)

@dataclass
class SivCourseManifest:
    nome_corso: str = "Corso SIV"
    data_inizio: str = ""
    data_fine: str = ""
    istruttore: str = ""
    luogo: str = ""
    piloti: List[PilotInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d['piloti'] = [p.to_dict() for p in self.piloti]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> 'SivCourseManifest':
        piloti_data = data.get('piloti', [])
        piloti = [PilotInfo.from_dict(p) for p in piloti_data]
        return cls(
            nome_corso=data.get('nome_corso', "Corso SIV"),
            data_inizio=data.get('data_inizio', ""),
            data_fine=data.get('data_fine', ""),
            istruttore=data.get('istruttore', ""),
            luogo=data.get('luogo', ""),
            piloti=piloti
        )

    def save(self, base_output_dir: str):
        os.makedirs(base_output_dir, exist_ok=True)
        manifest_path = os.path.join(base_output_dir, "corso_siv_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        # Salva anche pilota_info.json all'interno della cartella di ogni pilota
        for p in self.piloti:
            p_dir = os.path.join(base_output_dir, p.cartella)
            os.makedirs(p_dir, exist_ok=True)
            p_info_path = os.path.join(p_dir, "pilota_info.json")
            with open(p_info_path, "w", encoding="utf-8") as f:
                json.dump(p.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, base_output_dir: str) -> Optional['SivCourseManifest']:
        manifest_path = os.path.join(base_output_dir, "corso_siv_manifest.json")
        if not os.path.exists(manifest_path):
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.from_dict(data)
        except Exception:
            return None
