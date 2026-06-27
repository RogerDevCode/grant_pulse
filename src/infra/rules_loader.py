"""
Cargador y validador de archivos de reglas YAML para GrantPulse.
Asegura que los archivos de configuración por sitio cumplan estrictamente con las reglas de negocio.
"""

from pathlib import Path

import yaml
from pydantic import ValidationError as PydanticValidationError

from src.core.domain.entities import RulesConfig
from src.core.domain.exceptions import ConfigurationError
from src.infra.logging import get_logger

logger = get_logger(__name__)


def load_rules_from_yaml(filepath: Path) -> RulesConfig:
    """Lee y valida un archivo de configuración de reglas YAML.

    Lanza ConfigurationError si el archivo no existe, no es un YAML válido,
    o no cumple con el esquema RulesConfig.
    """
    if not filepath.exists():
        msg = f"El archivo de reglas no existe: {filepath}"
        logger.error(msg, filepath=str(filepath))
        raise ConfigurationError(msg)

    try:
        with open(filepath, encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        msg = f"Error de sintaxis YAML en {filepath.name}: {exc}"
        logger.error(msg, filepath=str(filepath), exc=exc)
        raise ConfigurationError(msg) from exc
    except Exception as exc:
        msg = f"Error al abrir el archivo de reglas {filepath.name}: {exc}"
        logger.error(msg, filepath=str(filepath), exc=exc)
        raise ConfigurationError(msg) from exc

    if not raw_data or not isinstance(raw_data, dict):
        msg = f"El archivo YAML no contiene un diccionario válido: {filepath.name}"
        logger.error(msg, filepath=str(filepath))
        raise ConfigurationError(msg)

    try:
        # Validación estricta con Pydantic
        rules_config = RulesConfig.model_validate(raw_data)
        logger.info(
            f"Configuración cargada y validada exitosamente: {rules_config.nombre}",
            source=rules_config.nombre,
        )
        return rules_config
    except PydanticValidationError as exc:
        msg = f"Fallo de validación de esquema en {filepath.name}: {exc.errors()}"
        logger.error(msg, filepath=str(filepath), errors=exc.errors())
        raise ConfigurationError(f"Esquema de reglas inválido en {filepath.name}: {exc}") from exc


def update_selectors_in_yaml(fuente_nombre: str, healed_selectors: dict[str, str]) -> None:
    """Busca el archivo YAML de la fuente y actualiza sus selectores permanentemente."""
    from pathlib import Path

    import yaml

    rules_dir = Path(__file__).parent.parent.parent / "rules"
    for filepath in rules_dir.glob("*.yaml"):
        try:
            with open(filepath, encoding="utf-8") as f:
                raw_data = yaml.safe_load(f)

            if raw_data and isinstance(raw_data, dict) and raw_data.get("nombre") == fuente_nombre:
                if "selectores" not in raw_data:
                    raw_data["selectores"] = {}

                # Actualizar los selectores
                for k, v in healed_selectors.items():
                    raw_data["selectores"][k] = v

                with open(filepath, "w", encoding="utf-8") as f:
                    yaml.safe_dump(raw_data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

                logger.info("Selectores sanados auto-guardados en YAML", filepath=str(filepath))
                return
        except Exception as exc:
            logger.warning("Fallo al intentar actualizar YAML con auto-healing", filepath=str(filepath), exc=exc)
