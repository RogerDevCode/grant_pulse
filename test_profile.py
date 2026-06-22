from pathlib import Path

from src.core.domain.entities import Fuente
from src.infra.cli import _apply_source_profile
from src.infra.rules_loader import load_rules_from_yaml

r = load_rules_from_yaml(Path("rules/corfo.yaml"))
f = Fuente(nombre=r.nombre, url_base=r.url_busqueda, configuracion_reglas=r, activa=r.activa)
print("A", f.id)
f2 = _apply_source_profile(f)
print("B", f2.id)
