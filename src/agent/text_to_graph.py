from src.agent.prompts import (
    NARRATIVE_ANALYZER_INSTRUCTION,
    ENTITY_RESOLUTION_AGENT_INSTRUCTION,
    EVENT_EXTRACTION_AGENT_INSTRUCTION,
    STATEMENT_EXTRACTION_AGENT_INSTRUCTION,
    TIME_RESOLUTION_AGENT_INSTRUCTION,
    CONTEXT_RESOLUTION_AGENT_2_INSTRUCTION,
    GRAPH_INTEGRATION_AGENT_INSTRUCTION,
    VALIDATION_AGENT_INSTRUCTION,
    ROOT_AGENT_INSTRUCTION
)
import json
from functools import cached_property
from typing import Any, Dict
from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import Client
from google.adk.tools import agent_tool
from google.adk import Context
from google.adk import Workflow
from google.adk.workflow import node
from tools.db_tools import execute_narrative_crud, generate_id_tool
class GlobalGemini(Gemini):
    """Pins the Vertex AI client to the `global` location.
    gemini-3 series models are only served from `global`; the default ADK
    `Gemini` integration constructs a `google.genai.Client` whose location
    defaults to the AgentEngine instance's region (e.g. `us-central1`) and
    fails with model-not-found for these models. Subclassing per the override
    pattern documented on `google.adk.models.google_llm.Gemini` lets the agent
    keep running in its regional AgentEngine instance while routing the model
    request to the global endpoint.
    """
    @cached_property
    def api_client(self) -> Client:
        return Client(vertexai=True, location="global")
# -----------------------------------------------------------------------------
# Sequential Pipeline Agents
# -----------------------------------------------------------------------------
narrative_analyzer = LlmAgent(
    name='narrative_analyzer',
    model='gemini-2.5-flash',
    description=(
        'Read a segment processed by the Ingestion Agent and produce a preliminary, pre-tagged representation of its narrative components.'
    ),
    sub_agents=[],
    instruction=NARRATIVE_ANALYZER_INSTRUCTION,
    tools=[execute_narrative_crud, generate_id_tool],
)
entity_resolution_agent = LlmAgent(
    name='entity_resolution_agent',
    model='gemini-2.5-flash',
    description=(
        'Map all mentions (pronouns, epithets, nicknames, common nouns) to unique, stable entities within the graph.'
    ),
    sub_agents=[],
    instruction=ENTITY_RESOLUTION_AGENT_INSTRUCTION,
    tools=[execute_narrative_crud, generate_id_tool],
)
event_extraction_agent = LlmAgent(
    name='event_extraction_agent',
    model='gemini-2.5-flash',
    description=(
        'transform actions and happenings in the text into event structures rich in contextual, causal, and temporal relations.'
    ),
    sub_agents=[],
    instruction=EVENT_EXTRACTION_AGENT_INSTRUCTION,
    tools=[execute_narrative_crud],
)
statement_extraction_agent = LlmAgent(
    name='statement_extraction_agent',
    model='gemini-2.5-flash',
    description=(
        'Break down descriptions, attributes, roles, and contextual information into atomic, verifiable triples (Subject — Predicate — Object).'
    ),
    sub_agents=[],
    instruction=STATEMENT_EXTRACTION_AGENT_INSTRUCTION,
    tools=[execute_narrative_crud],
)
time_resolution_agent = LlmAgent(
    name='time_resolution_agent',
    model='gemini-2.5-flash',
    description=(
        'Model the chronology of the story, managing relative time, intervals, and story order (diegesis vs. discourse order).'
    ),
    sub_agents=[],
    instruction=TIME_RESOLUTION_AGENT_INSTRUCTION,
    tools=[execute_narrative_crud],
)
context_resolution_agent_2 = LlmAgent(
    name='context_resolution_agent_2',
    model='gemini-2.5-flash',
    description=(
        'Determine the validity or ontological origin of statements and events (discerning whether they are objective facts within the story world or subjective beliefs, lies, prophecies, rumors, or dreams).'
    ),
    sub_agents=[],
    instruction=CONTEXT_RESOLUTION_AGENT_2_INSTRUCTION,
    tools=[execute_narrative_crud],
)
graph_integration_agent = LlmAgent(
    name='graph_integration_agent',
    model='gemini-2.5-flash',
    description=(
        'Take resolved entities, events, statements, temporal data, and context to generate an ordered list of ATOMIC GRAPH OPERATIONS.'
    ),
    sub_agents=[],
    instruction=GRAPH_INTEGRATION_AGENT_INSTRUCTION,
    tools=[execute_narrative_crud],
)
validation_agent = LlmAgent(
    name='validation_agent',
    model='gemini-2.5-flash',
    description=(
        'Act as the final quality control gate before operations are executed or permanently persisted into the graph.'
    ),
    sub_agents=[],
    instruction=VALIDATION_AGENT_INSTRUCTION,
    tools=[execute_narrative_crud],
)
# -----------------------------------------------------------------------------
# Root Agent
# -----------------------------------------------------------------------------
ingestion_agent = LlmAgent(
    name='Ingestion_Agent',
    model=GlobalGemini(model='gemini-3.5-flash'),
    description=(
        'Receive raw text, detect its structural hierarchy, and segment the text without interpreting or summarizing the plot.'
    ),
    sub_agents=[
        narrative_analyzer,
        entity_resolution_agent,
        event_extraction_agent,
        statement_extraction_agent,
        time_resolution_agent,
        context_resolution_agent_2,
        graph_integration_agent,
        validation_agent
    ],
    instruction=ROOT_AGENT_INSTRUCTION,
    tools=[],
)

# -----------------------------------------------------------------------------
# Pipeline Execution Logic
# -----------------------------------------------------------------------------
SEQUENTIAL_AGENTS = [
    narrative_analyzer,
    entity_resolution_agent,
    event_extraction_agent,
    statement_extraction_agent,
    time_resolution_agent,
    context_resolution_agent_2,
    graph_integration_agent,
    validation_agent
]

@node(name="run_ingestion_sequence", rerun_on_resume=True)
async def run_ingestion_sequence(ctx: Context, node_input: str) -> Dict[str, Any]:
    """
    Executes the ingestion pipeline.
    1. Uses ingestion_agent to segment the text.
    2. Sequentially executes the downstream agents for each segment,
       passing the cumulative results along.
    """
    print("Running Ingestion Agent for text segmentation...")
    try:
        # Correctly call the LlmAgent using ctx.run_node
        segmentation_result = await ctx.run_node(ingestion_agent, node_input=node_input)
        
        # Handle depending on whether result is JSON string or dict
        if isinstance(segmentation_result, str):
            segmentation_data = json.loads(segmentation_result)
        else:
            segmentation_data = segmentation_result
    except Exception as e:
        print(f"Error during segmentation: {e}")
        return {"error": str(e)}

    pipeline_results = {
        "segmentation": segmentation_data,
        "segments_analysis": {}
    }
    
    # Iterate through the hierarchy and process each segment
    structure = segmentation_data.get("hierarchy", {}).get("structure", [])
    for chapter in structure:
        for scene in chapter.get("scenes", []):
            for segment in scene.get("segments", []):
                seg_id = segment.get("segmentId")
                seg_content = segment.get("content", "")
                print(f"Processing segment: {seg_id}")
                cumulative_context = {
                    "segmentId": seg_id,
                    "content": seg_content,
                    "results": {}
                }
                
                # Run the sequence of sub-agents on the segment
                for agent in SEQUENTIAL_AGENTS:
                    print(f"  -> Running agent: {agent.name}")
                    # Prepare prompt using previous results
                    prompt = f"Analyze this segment context:\n{json.dumps(cumulative_context, indent=2)}"
                    try:
                        # Correctly call downstream agents using ctx.run_node
                        agent_result = await ctx.run_node(agent, node_input=prompt)
                        
                        # Store result to be passed to next agent
                        if isinstance(agent_result, str):
                            try:
                                cumulative_context["results"][agent.name] = json.loads(agent_result)
                            except json.JSONDecodeError:
                                cumulative_context["results"][agent.name] = agent_result
                        else:
                            cumulative_context["results"][agent.name] = agent_result
                    except Exception as e:
                        print(f"  -> Error in {agent.name}: {e}")
                        cumulative_context["results"][agent.name] = {"error": str(e)}
                        
                pipeline_results["segments_analysis"][seg_id] = cumulative_context
                
    return pipeline_results

# Define the workflow that starts the ingestion sequence
root_agent = Workflow(
    name='root_workflow',
    edges=[("START", run_ingestion_sequence)],
)