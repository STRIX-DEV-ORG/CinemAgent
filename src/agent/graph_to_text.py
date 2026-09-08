import json
from functools import cached_property
from typing import Any, Dict, List
from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.genai import Client
from google.adk import Context
from google.adk import Workflow
from google.adk.workflow import node

from src.agent.prompts import (
    GRAPH_RETRIEVAL_AGENT_INSTRUCTION,
    NARRATIVE_PLANNER_INSTRUCTION,
    SCENE_PLANNER_INSTRUCTION,
    PROSE_WRITER_INSTRUCTION,
    STYLE_AGENT_INSTRUCTION,
    NARRATIVE_CONSISTENCY_AGENT_INSTRUCTION,
    GRAPH_FEEDBACK_AGENT_INSTRUCTION,
    STORY_REQUEST_INTERPRETER_INSTRUCTION,
)
from src.agent.tools.narrative_api import query_narrative_subgraph, submit_narrative_operations, get_operation_batch
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
# Graph-to-Text Pipeline Agents
# -----------------------------------------------------------------------------

graph_retrieval_agent = LlmAgent(
    name='graph_retrieval_agent',
    model='gemini-2.5-flash',
    description=(
        'Queries the global knowledge graph to extract only the specific subgraph relevant to the requested story constraints, enforcing strict epistemic boundaries (preventing character knowledge leaks).'
    ),
    sub_agents=[],
    instruction=GRAPH_RETRIEVAL_AGENT_INSTRUCTION,
    tools=[query_narrative_subgraph],
)

narrative_planner = LlmAgent(
    name='narrative_planner',
    model='gemini-2.5-flash',
    description=(
        'Transforms the retrieved subgraph into a structured, high-level narrative outline (multi-act structure or plot sequence), prioritizing narrative tension, pacing, and causal flow.'
    ),
    sub_agents=[],
    instruction=NARRATIVE_PLANNER_INSTRUCTION,
    tools=[],
)

scene_planner = LlmAgent(
    name='scene_planner',
    model='gemini-2.5-flash',
    description=(
        'Deconstructs high-level narrative beats into execution-ready scene blueprints (ScenePlan), establishing settings, active characters, explicit facts to reveal or hide, and desired dramaturgical outcomes.'
    ),
    sub_agents=[],
    instruction=SCENE_PLANNER_INSTRUCTION,
    tools=[],
)

prose_writer = LlmAgent(
    name='prose_writer',
    model='gemini-2.5-flash',
    description=(
        'Translates a single ScenePlan into rich narrative prose while adhering strictly to provided graph facts and tracking any newly invented ornamental details.'
    ),
    sub_agents=[],
    instruction=PROSE_WRITER_INSTRUCTION,
    tools=[],
)

style_agent = LlmAgent(
    name='style_agent',
    model='gemini-2.5-flash',
    description=(
        'Refines raw draft prose to enhance voice, rhythm, vocabulary, and dialogue authentic to the target genre without altering underlying facts or scene outcomes.'
    ),
    sub_agents=[],
    instruction=STYLE_AGENT_INSTRUCTION,
    tools=[],
)

narrative_consistency_agent = LlmAgent(
    name='narrative_consistency_agent',
    model='gemini-2.5-flash',
    description=(
        'Audits generated prose against the Knowledge Graph and Scene Plan to detect continuity errors, character perspective leaks, temporal paradoxes, or dead characters acting.'
    ),
    sub_agents=[],
    instruction=NARRATIVE_CONSISTENCY_AGENT_INSTRUCTION,
    tools=[query_narrative_subgraph],
)

graph_feedback_agent = LlmAgent(
    name='graph_feedback_agent',
    model='gemini-2.5-flash',
    description=(
        'Analyzes novel elements introduced during prose writing (ornamental items, minor actions, new locations) and proposes formal graph mutations to keep the Knowledge Graph updated (completing the bidirectional loop).'
    ),
    sub_agents=[],
    instruction=GRAPH_FEEDBACK_AGENT_INSTRUCTION,
    tools=[submit_narrative_operations, get_operation_batch],
)

# -----------------------------------------------------------------------------
# Root Agent
# -----------------------------------------------------------------------------

story_request_interpreter = LlmAgent(
    name='Story_Request_Interpreter',
    model=GlobalGemini(model='gemini-3.5-flash'),
    description=(
        'Translates informal natural language user requests into precise narrative generation constraints (StoryRequest), establishing protagonists, perspectives, scope, genre, tone, and knowledge boundaries.'
    ),
    sub_agents=[
        graph_retrieval_agent,
        narrative_planner,
        scene_planner,
        prose_writer,
        style_agent,
        narrative_consistency_agent,
        graph_feedback_agent
    ],
    instruction=STORY_REQUEST_INTERPRETER_INSTRUCTION,
    tools=[],
)

# Helper for JSON parsing
def _parse_agent_output(result: Any) -> Any:
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    return result


# -----------------------------------------------------------------------------
# Pipeline Execution Logic
# -----------------------------------------------------------------------------

@node(name="run_generation_sequence", rerun_on_resume=True)
async def run_generation_sequence(ctx: Context, node_input: str) -> Dict[str, Any]:
    """
    Executes the Graph-to-Text generation pipeline.
    1. Interprets natural language request into a StoryRequest.
    2. Retrieves perspective-isolated subgraph.
    3. Plans multi-act narrative structure.
    4. Generates granular scene blueprints.
    5. For each scene:
       - Drafts prose with invention tracking
       - Polishes prose for voice & style
       - Audits consistency against graph & POV rules
       - Proposes graph feedback mutations to complete bidirectional loop.
    """
    print("Running Story Request Interpreter...")
    try:
        interpreter_result = await ctx.run_node(story_request_interpreter, node_input=node_input)
        story_request = _parse_agent_output(interpreter_result)
    except Exception as e:
        print(f"Error in story request interpretation: {e}")
        return {"error": f"Story interpretation failed: {str(e)}"}

    print("Running Graph Retrieval Agent...")
    try:
        retrieval_prompt = f"Extract relevant subgraph for this StoryRequest:\n{json.dumps(story_request, indent=2)}"
        retrieval_result = await ctx.run_node(graph_retrieval_agent, node_input=retrieval_prompt)
        subgraph = _parse_agent_output(retrieval_result)
    except Exception as e:
        print(f"Error in graph retrieval: {e}")
        subgraph = {"error": str(e)}

    print("Running Narrative Planner...")
    try:
        narrative_prompt = (
            f"Create a narrative outline based on:\n"
            f"StoryRequest:\n{json.dumps(story_request, indent=2)}\n\n"
            f"Subgraph:\n{json.dumps(subgraph, indent=2)}"
        )
        narrative_result = await ctx.run_node(narrative_planner, node_input=narrative_prompt)
        narrative_outline = _parse_agent_output(narrative_result)
    except Exception as e:
        print(f"Error in narrative planning: {e}")
        narrative_outline = {"error": str(e)}

    print("Running Scene Planner...")
    try:
        scene_prompt = (
            f"Generate scene blueprints based on:\n"
            f"NarrativeOutline:\n{json.dumps(narrative_outline, indent=2)}\n\n"
            f"Subgraph:\n{json.dumps(subgraph, indent=2)}"
        )
        scene_result = await ctx.run_node(scene_planner, node_input=scene_prompt)
        scene_plans_data = _parse_agent_output(scene_result)
    except Exception as e:
        print(f"Error in scene planning: {e}")
        scene_plans_data = {"error": str(e)}

    # Extract list of scene plans
    scene_plans = []
    if isinstance(scene_plans_data, dict):
        scene_plans = scene_plans_data.get("scenePlans", [])
    elif isinstance(scene_plans_data, list):
        scene_plans = scene_plans_data

    scenes_generation: Dict[str, Any] = {}
    final_prose_pieces: List[str] = []

    # Process each scene plan sequentially through generation, styling, audit, and feedback
    for idx, scene_plan in enumerate(scene_plans):
        scene_id = scene_plan.get("id", f"scene_plan_{idx+1}") if isinstance(scene_plan, dict) else f"scene_plan_{idx+1}"
        print(f"Processing Scene: {scene_id}")

        scene_context: Dict[str, Any] = {
            "sceneId": scene_id,
            "scenePlan": scene_plan,
            "subgraph": subgraph,
            "results": {}
        }

        # 1. Prose Writer
        print(f"  -> Running Prose Writer for {scene_id}...")
        prose_prompt = (
            f"Write draft narrative prose for this scene blueprint:\n"
            f"ScenePlan:\n{json.dumps(scene_plan, indent=2)}\n\n"
            f"Available Subgraph Context:\n{json.dumps(subgraph, indent=2)}"
        )
        try:
            prose_raw = await ctx.run_node(prose_writer, node_input=prose_prompt)
            prose_result = _parse_agent_output(prose_raw)
            scene_context["results"]["prose_writer"] = prose_result
        except Exception as e:
            print(f"  -> Error in prose writer: {e}")
            scene_context["results"]["prose_writer"] = {"error": str(e)}

        draft_prose = ""
        proposed_inventions = []
        if isinstance(scene_context["results"]["prose_writer"], dict):
            draft_prose = scene_context["results"]["prose_writer"].get("prose", "")
            proposed_inventions = scene_context["results"]["prose_writer"].get("proposedInventions", [])

        # 2. Style Agent
        print(f"  -> Running Style Agent for {scene_id}...")
        style_prompt = (
            f"Polish this raw draft prose according to genre and tone constraints:\n"
            f"Genre: {story_request.get('genre', 'general') if isinstance(story_request, dict) else 'general'}\n"
            f"Tone: {story_request.get('tone', 'neutral') if isinstance(story_request, dict) else 'neutral'}\n"
            f"Draft Prose:\n{draft_prose}"
        )
        try:
            style_raw = await ctx.run_node(style_agent, node_input=style_prompt)
            style_result = _parse_agent_output(style_raw)
            scene_context["results"]["style_agent"] = style_result
        except Exception as e:
            print(f"  -> Error in style agent: {e}")
            scene_context["results"]["style_agent"] = {"error": str(e)}

        polished_prose = draft_prose
        if isinstance(scene_context["results"]["style_agent"], dict):
            polished_prose = scene_context["results"]["style_agent"].get("polishedProse", draft_prose)

        # 3. Narrative Consistency Agent
        print(f"  -> Running Narrative Consistency Agent for {scene_id}...")
        consistency_prompt = (
            f"Audit the polished scene prose for continuity, POV leaks, and graph consistency:\n"
            f"ScenePlan:\n{json.dumps(scene_plan, indent=2)}\n\n"
            f"Polished Prose:\n{polished_prose}\n\n"
            f"Master Subgraph:\n{json.dumps(subgraph, indent=2)}"
        )
        try:
            consistency_raw = await ctx.run_node(narrative_consistency_agent, node_input=consistency_prompt)
            scene_context["results"]["narrative_consistency_agent"] = _parse_agent_output(consistency_raw)
        except Exception as e:
            print(f"  -> Error in consistency agent: {e}")
            scene_context["results"]["narrative_consistency_agent"] = {"error": str(e)}

        # 4. Graph Feedback Agent
        print(f"  -> Running Graph Feedback Agent for {scene_id}...")
        feedback_prompt = (
            f"Analyze scene prose and proposed inventions for canonical graph mutations:\n"
            f"Scene Prose:\n{polished_prose}\n\n"
            f"Proposed Inventions:\n{json.dumps(proposed_inventions, indent=2)}"
        )
        try:
            feedback_raw = await ctx.run_node(graph_feedback_agent, node_input=feedback_prompt)
            scene_context["results"]["graph_feedback_agent"] = _parse_agent_output(feedback_raw)
        except Exception as e:
            print(f"  -> Error in graph feedback agent: {e}")
            scene_context["results"]["graph_feedback_agent"] = {"error": str(e)}

        scenes_generation[scene_id] = scene_context
        if polished_prose:
            final_prose_pieces.append(polished_prose)

    pipeline_results = {
        "story_request": story_request,
        "subgraph": subgraph,
        "narrative_outline": narrative_outline,
        "scene_plans": scene_plans_data,
        "scenes_generation": scenes_generation,
        "final_narrative": "\n\n".join(final_prose_pieces)
    }

    return pipeline_results


# Define the workflow that starts the graph-to-text sequence
root_agent = Workflow(
    name='graph_to_text_workflow',
    edges=[("START", run_generation_sequence)],
)
