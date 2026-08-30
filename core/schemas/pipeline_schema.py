
from pydantic import BaseModel

from core.schemas.process_graph import Connection, Unit


class PipelineInterface(BaseModel):
    observation_inputs: list[object]
    action_output: dict[str, object]
    params_unit_id: str


class PipelineTemplate(BaseModel):
    units: list[Unit]
    connections: list[Connection]
    pipeline_interface: PipelineInterface
