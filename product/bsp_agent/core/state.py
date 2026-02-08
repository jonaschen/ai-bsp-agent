from typing import TypedDict, List, Annotated, Union, Optional
from product.bsp_agent.core.schema import ConsultantResponse

class AgentState(TypedDict):
    messages: List[Union[tuple, str]]
    current_log_chunk: Optional[str]
    diagnosis_report: Optional[ConsultantResponse]
