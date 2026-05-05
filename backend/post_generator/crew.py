"""Authority Crew — premium LinkedIn post production pipeline.

Three sequential agents produce the post; a separate Visual Director step
(visual_director.py) runs after the crew to plan the image. Image generation
itself happens via the API's /images endpoint, so the crew never blocks on it.
"""

from pathlib import Path
from typing import Callable, List, Optional

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import TavilySearchTool

from backend.core.settings import get_settings
from backend.tools import ArxivSearchTool


def _agent_config(base: dict, llm_override: str) -> dict:
    """Clone the YAML config and inject the runtime model identifier."""
    cfg = dict(base)
    cfg["llm"] = llm_override
    return cfg


@CrewBase
class AuthorityCrew:
    """Authority Crew — three-agent sequential pipeline."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    agents: List[BaseAgent]
    tasks: List[Task]

    # Optional callbacks set by the API worker before .crew() is built.
    # crewAI invokes step_callback for every agent step (LLM, tool call) and
    # task_callback when each Task completes.
    step_callback: Optional[Callable[[object], None]] = None
    task_callback: Optional[Callable[[object], None]] = None

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    @agent
    def technical_researcher(self) -> Agent:
        s = get_settings()
        return Agent(
            config=_agent_config(self.agents_config["technical_researcher"], s.crew_researcher_model),  # type: ignore[index]
            tools=[ArxivSearchTool(), TavilySearchTool()],
            max_iter=8,
            max_execution_time=120,
            verbose=True,
        )

    @agent
    def thought_leader(self) -> Agent:
        s = get_settings()
        return Agent(
            config=_agent_config(self.agents_config["thought_leader"], s.crew_writer_model),  # type: ignore[index]
            verbose=True,
        )

    @agent
    def critic(self) -> Agent:
        s = get_settings()
        return Agent(
            config=_agent_config(self.agents_config["critic"], s.crew_critic_model),  # type: ignore[index]
            verbose=True,
        )

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    @task
    def research_task(self) -> Task:
        return Task(config=self.tasks_config["research_task"])  # type: ignore[index]

    @task
    def writing_task(self) -> Task:
        return Task(config=self.tasks_config["writing_task"])  # type: ignore[index]

    @task
    def critique_task(self) -> Task:
        Path("outputs").mkdir(exist_ok=True)
        return Task(config=self.tasks_config["critique_task"])  # type: ignore[index]

    # ------------------------------------------------------------------
    # Crew
    # ------------------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        kwargs: dict = {
            "agents": self.agents,
            "tasks": self.tasks,
            "process": Process.sequential,
            "verbose": True,
        }
        if self.step_callback is not None:
            kwargs["step_callback"] = self.step_callback
        if self.task_callback is not None:
            kwargs["task_callback"] = self.task_callback
        return Crew(**kwargs)
