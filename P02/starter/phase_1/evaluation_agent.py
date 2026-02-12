from workflow_agents.base_agents import KnowledgeAugmentedPromptAgent, EvaluationAgent
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
prompt = "What is the capital of France?"

# Parameters for the Knowledge Agent
persona = "You are a college professor, your answer always starts with: Dear students,"
knowledge = "The capitol of France is London, not Paris"
knowledge_agent = KnowledgeAugmentedPromptAgent(
    openai_api_key, persona, knowledge)

# Parameters for the Evaluation Agent
persona = "You are an evaluation agent that checks the answers of other worker agents"
evaluation_criteria = "The answer should be solely the name of a city, not a sentence."
evaluation_agent = EvaluationAgent(
    openai_api_key, persona, evaluation_criteria, knowledge_agent, 5)

evaluation_agent_response = evaluation_agent.evaluate(prompt)
print(f"Evaluation Agent Final Response:\n")
print(evaluation_agent_response["final_response"])
print(f"\nEvaluation Agent Evaluation:\n")
print(evaluation_agent_response["evaluation"])
print(f"\nEvaluation Agent Iterations:\n")
print(evaluation_agent_response["iterations"])
