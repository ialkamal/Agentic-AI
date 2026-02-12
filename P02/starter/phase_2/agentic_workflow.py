# agentic_workflow.py

from workflow_agents.base_agents import ActionPlanningAgent, KnowledgeAugmentedPromptAgent, EvaluationAgent, RoutingAgent

import os
from dotenv import load_dotenv

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, "Product-Spec-Email-Router.txt"), "r") as file:
    product_spec = file.read()

# Instantiate all the agents

# Action Planning Agent
knowledge_action_planning = (
    "Stories are defined from a product spec by identifying a "
    "persona, an action, and a desired outcome for each story. "
    "Each story represents a specific functionality of the product "
    "described in the specification. \n"
    "Features are defined by grouping related user stories. \n"
    "Tasks are defined for each story and represent the engineering "
    "work required to develop the product. \n"
    "A development Plan for a product contains all these components"
)
action_planning_agent = ActionPlanningAgent(openai_api_key, knowledge_action_planning)

# Product Manager - Knowledge Augmented Prompt Agent
persona_product_manager = "You are a Product Manager, you are responsible for defining the user stories for a product."
knowledge_product_manager = (
    "Stories are defined by writing sentences with a persona, an action, and a desired outcome. "
    "The sentences always start with: As a "
    "Write several stories for the product spec below, where the personas are the different users of the product. "
    f"{product_spec}"
)
product_manager_knowledge_agent = KnowledgeAugmentedPromptAgent(openai_api_key, persona_product_manager, knowledge_product_manager)

# Product Manager - Evaluation Agent
product_manager_evaluation_agent = EvaluationAgent(
    openai_api_key, 
    "You are an evaluation agent that checks the answers of other worker agents.", 
    "The answer should be user stories following the structure: 'As a [type of user], I want [an action or feature] so that [benefit/value].'", 
    product_manager_knowledge_agent, 5)

# Program Manager - Knowledge Augmented Prompt Agent
persona_program_manager = "You are a Program Manager, you are responsible for defining the features for a product."
knowledge_program_manager = "Features of a product are defined by organizing similar user stories into cohesive groups."
# Instantiate a program_manager_knowledge_agent using 'persona_program_manager' and 'knowledge_program_manager'
# (This is a necessary step before TODO 8. Students should add the instantiation code here.)
program_manager_knowledge_agent = KnowledgeAugmentedPromptAgent(openai_api_key, persona_program_manager, knowledge_program_manager)

# Program Manager - Evaluation Agent
persona_program_manager_eval = "You are an evaluation agent that checks the answers of other worker agents."

# Instantiate a program_manager_evaluation_agent using 'persona_program_manager_eval' and the evaluation criteria below.
#                      "The answer should be product features that follow the following structure: " \
#                      "Feature Name: A clear, concise title that identifies the capability\n" \
#                      "Description: A brief explanation of what the feature does and its purpose\n" \
#                      "Key Functionality: The specific capabilities or actions the feature provides\n" \
#                      "User Benefit: How this feature creates value for the user"
# For the 'agent_to_evaluate' parameter, refer to the provided solution code's pattern.

program_manager_evaluation_agent = EvaluationAgent(
    openai_api_key, 
    persona_program_manager_eval, 
    "The answer should be product features that follow the following structure:" \
    "Feature Name: A clear, concise title that identifies the capability\n" \
    "Description: A brief explanation of what the feature does and its purpose\n" \
    "Key Functionality: The specific capabilities or actions the feature provides\n" \
    "User Benefit: How this feature creates value for the user", 
    program_manager_knowledge_agent, 5)

# Development Engineer - Knowledge Augmented Prompt Agent
persona_dev_engineer = "You are a Development Engineer, you are responsible for defining the development tasks for a product."
knowledge_dev_engineer = "Development tasks are defined by identifying what needs to be built to implement each user story."
# Instantiate a development_engineer_knowledge_agent using 'persona_dev_engineer' and 'knowledge_dev_engineer'
development_engineer_knowledge_agent = KnowledgeAugmentedPromptAgent(openai_api_key, persona_dev_engineer, knowledge_dev_engineer)

# Development Engineer - Evaluation Agent
persona_dev_engineer_eval = "You are an evaluation agent that checks the answers of other worker agents."
# Instantiate a development_engineer_evaluation_agent using 'persona_dev_engineer_eval' and the evaluation criteria below.
                    #  "The answer should be tasks following this exact structure: " \
                    #  "Task ID: A unique identifier for tracking purposes\n" \
                    #  "Task Title: Brief description of the specific development work\n" \
                    #  "Related User Story: Reference to the parent user story\n" \
                    #  "Description: Detailed explanation of the technical work required\n" \
                    #  "Acceptance Criteria: Specific requirements that must be met for completion\n" \
                    #  "Estimated Effort: Time or complexity estimation\n" \
                    #  "Dependencies: Any tasks that must be completed first"
# For the 'agent_to_evaluate' parameter, refer to the provided solution code's pattern.
development_engineer_evaluation_agent = EvaluationAgent(
    openai_api_key, 
    persona_dev_engineer_eval, 
    "The answer should be tasks following this exact structure: " \
    "Task ID: A unique identifier for tracking purposes\n" \
    "Task Title: Brief description of the specific development work\n" \
    "Related User Story: Reference to the parent user story\n" \
    "Description: Detailed explanation of the technical work required\n" \
    "Acceptance Criteria: Specific requirements that must be met for completion\n" \
    "Estimated Effort: Time or complexity estimation\n" \
    "Dependencies: Any tasks that must be completed first",
    development_engineer_knowledge_agent, 5)

# Routing Agent
# Instantiate a routing_agent. You will need to define a list of agent dictionaries (routes) for Product Manager, Program Manager, and Development Engineer. Each dictionary should contain 'name', 'description', and 'func' (linking to a support function). Assign this list to the routing_agent's 'agents' attribute.
agents_list = [
    {
        "name": "Product Manager",
        "description": "defining user stories for a product",
        "func": lambda x : product_manager_support_function(x)
    },
    {
        "name": "Program Manager",
        "description": "Define features based on user stories for the product",
        "func": lambda x : program_manager_support_function(x)
    },
    {
        "name": "Development Engineer",
        "description": "Break down the engineering work required to develop the product for each user story under the given features",
        "func": lambda x : development_engineer_support_function(x)
    }
]
routing_agent = RoutingAgent(openai_api_key, agents_list)

# Job function persona support functions
# Define the support functions for the routes of the routing agent (e.g., product_manager_support_function, program_manager_support_function, development_engineer_support_function).
# Each support function should:
#   1. Take the input query (e.g., a step from the action plan).
#   2. Get a response from the respective Knowledge Augmented Prompt Agent.
#   3. Have the response evaluated by the corresponding Evaluation Agent.
#   4. Return the final validated response.
def product_manager_support_function(input):
    response = product_manager_knowledge_agent.respond(input)
    evaluation = product_manager_evaluation_agent.evaluate(response)
    if evaluation:
        return evaluation["final_response"]
    else:
        return "The response did not meet the evaluation criteria."

def program_manager_support_function(input):
    response = program_manager_knowledge_agent.respond(input)
    evaluation = program_manager_evaluation_agent.evaluate(response)
    if evaluation:
        return evaluation["final_response"]
    else:
        return "The response did not meet the evaluation criteria."
    
def development_engineer_support_function(input):
    response = development_engineer_knowledge_agent.respond(input)
    evaluation = development_engineer_evaluation_agent.evaluate(response)
    if evaluation:
        return evaluation["final_response"]
    else:
        return "The response did not meet the evaluation criteria."

# Run the workflow

print("\n*** Workflow execution started ***\n")
# Workflow Prompt
# ****
workflow_prompt = "What would the development tasks for this product be? Only provide the list of steps grouped into 3 steps."
# ****
print(f"Task to complete in this workflow, workflow prompt = {workflow_prompt}")

print("\nDefining workflow steps from the workflow prompt")
# Implement the workflow.
#   1. Use the 'action_planning_agent' to extract steps from the 'workflow_prompt'.
#   2. Initialize an empty list to store 'completed_steps'.
#   3. Loop through the extracted workflow steps:
#      a. For each step, use the 'routing_agent' to route the step to the appropriate support function.
#      b. Append the result to 'completed_steps'.
#      c. Print information about the step being executed and its result.
#   4. After the loop, print the final output of the workflow (the last completed step).

workflow_steps = action_planning_agent.extract_steps_from_prompt(workflow_prompt)
completed_steps = []
result = ""
print(workflow_steps)
for i,step in enumerate(workflow_steps):
    print("\n================================\n")
    print(f"Executing workflow step: {step}")
    print("\n================================\n")
    result = routing_agent.route(step + " " + result)
    completed_steps.append(result)
    if i == len(workflow_steps) - 1:
        print(f"\nFinal Output of the workflow:\n{result}")
    else:
        print(f"Result of step:\n{result}\n")
        print(f"Moving to the next step...\n")