from workflow_agents.base_agents import RoutingAgent, KnowledgeAugmentedPromptAgent
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")

persona = "You are a college professor"

knowledge = "You know everything about Texas"
knowledge_agent_texas = KnowledgeAugmentedPromptAgent(openai_api_key, persona, knowledge)

knowledge = "You know everything about Europe"
knowledge_agent_europe = KnowledgeAugmentedPromptAgent(openai_api_key, persona, knowledge)

persona = "You are a college math professor"
knowledge = "You know everything about math, you take prompts with numbers, extract math formulas, and show the answer without explanation"
knowledge_agent_math = KnowledgeAugmentedPromptAgent(openai_api_key, persona, knowledge)

routing_agent = RoutingAgent(openai_api_key,[])
agents = [
    {
        "name": "texas agent",
        "description": "Answer a question about Texas",
        "func": lambda x: knowledge_agent_texas.respond(x)
    },
    {
        "name": "europe agent",
        "description": "Answer a question about Europe",
        "func": lambda x: knowledge_agent_europe.respond(x)
    },
    {
        "name": "math agent",
        "description": "When a prompt contains numbers, respond with a math formula",
        "func": lambda x: knowledge_agent_math.respond(x)
    }
]

routing_agent.agents = agents

print("Response to 'Tell me about the history of Rome, Texas':")
response = routing_agent.route("Tell me about the history of Rome, Texas")
print(response)

print("Response to 'Tell me about the history of Rome, Italy':")
response = routing_agent.route("Tell me about the history of Rome, Italy")
print(response)

print("Response to 'One story takes 2 days, and there are 20 stories':")
response = routing_agent.route("One story takes 2 days, and there are 20 stories")
print(response)