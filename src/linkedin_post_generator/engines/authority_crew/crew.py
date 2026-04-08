"""
Engine 2: Authority Crew — Premium LinkedIn Post Production

Multi-agent cascade:
  1. Technical Researcher (GPT-4o)    → Fact Sheet
  2. Thought Leader (Claude 3.5 Sonnet) → LinkedIn post draft
  3. Critic & Visual Director (GPT-4o) → Fact-check + DALL-E image
"""

from pathlib import Path
from typing import List

from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import TavilySearchTool

from linkedin_post_generator.tools import ArxivSearchTool


@CrewBase
class AuthorityCrew:
    """Authority Crew — Premium LinkedIn post production pipeline."""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    agents: List[BaseAgent]
    tasks: List[Task]

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    @agent
    def technical_researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["technical_researcher"],  # type: ignore[index]
            tools=[
                ArxivSearchTool(),
                TavilySearchTool(),
            ],
            verbose=True,
        )

    @agent
    def thought_leader(self) -> Agent:
        return Agent(
            config=self.agents_config["thought_leader"],  # type: ignore[index]
            verbose=True,
        )

    @agent
    def critic_visual_director(self) -> Agent:
        return Agent(
            config=self.agents_config["critic_visual_director"],  # type: ignore[index]
            tools=[
                TavilySearchTool(),
            ],
            verbose=True,
        )

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    @task
    def research_task(self) -> Task:
        return Task(
            config=self.tasks_config["research_task"],  # type: ignore[index]
        )

    @task
    def writing_task(self) -> Task:
        return Task(
            config=self.tasks_config["writing_task"],  # type: ignore[index]
        )

    @task
    def critique_task(self) -> Task:
        # Ensure output dir exists
        Path("outputs").mkdir(exist_ok=True)
        return Task(
            config=self.tasks_config["critique_task"],  # type: ignore[index]
        )

    # ------------------------------------------------------------------
    # Crew
    # ------------------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
