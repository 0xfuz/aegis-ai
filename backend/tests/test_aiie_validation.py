import json
import pytest
from pydantic import ValidationError
from app.modules.ai_reasoning.domain.intelligence_service import Output

def valid(): return {"summary":"s","observations":[{"statement":"o","confidence":50,"supporting_facts":["EN1"]}],"hypotheses":[],"recommendations":[],"questions":[],"reasoning":[]}
def test_valid_structured_output(): assert Output.model_validate(valid()).summary=="s"
@pytest.mark.parametrize("mutate",[lambda x:x.update(extra="x"),lambda x:x["observations"][0].update(unknown="x"),lambda x:x["observations"][0].update(confidence=101),lambda x:x["observations"][0].update(confidence="50")])
def test_rejects_malformed_structured_output(mutate):
 data=valid();mutate(data)
 with pytest.raises(ValidationError): Output.model_validate(data)
