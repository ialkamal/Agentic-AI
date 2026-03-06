from openai import OpenAI
import numpy as np
import pandas as pd
import re
import csv
import uuid
from datetime import datetime


class DirectPromptAgent:
    """Minimal agent that forwards a raw prompt to the LLM with no extra context."""

    def __init__(self, openai_api_key):
        """Store API credentials for later calls."""
        self.openai_api_key = openai_api_key

    def respond(self, prompt):
        """Send *prompt* directly to the LLM and return the response text."""
        client = OpenAI(
                        base_url = "https://openai.vocareum.com/v1",
                        api_key = self.openai_api_key
                        )
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role":"user",
                    "content": prompt
                }
            ],
            temperature=0
        )
        return response.choices[0].message.content

        

class AugmentedPromptAgent:
    """Agent that prepends a persona-based system prompt before querying the LLM."""

    def __init__(self, openai_api_key, persona):
        """Store API credentials and the persona system prompt."""
        self.persona = persona
        self.openai_api_key = openai_api_key

    def respond(self, input_text):
        """Generate a persona-augmented response for *input_text*."""
        client = OpenAI(
                        base_url = "https://openai.vocareum.com/v1",
                        api_key = self.openai_api_key
                        )

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": self.persona + "You must forget previous context."},
                {"role": "user", "content": input_text}
            ],
            temperature=0
        )
        return response.choices[0].message.content



class KnowledgeAugmentedPromptAgent:
    """Agent that constrains LLM answers to a supplied knowledge block.

    The system prompt instructs the model to ignore its own training data
    and answer exclusively from the injected *knowledge* string.
    """

    def __init__(self, openai_api_key, persona, knowledge):
        """Store API credentials, persona, and the knowledge to ground answers on."""
        self.persona = persona
        self.knowledge = knowledge
        self.openai_api_key = openai_api_key

    def respond(self, input_text):
        """Return an LLM response grounded only in *self.knowledge*."""
        client = OpenAI(
                        base_url = "https://openai.vocareum.com/v1",
                        api_key = self.openai_api_key
                        )
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"You are {self.persona} knowledge-based assistant. Forget all previous context. Use only the following knowledge to answer, do not use your own knowledge: {self.knowledge}. Answer the prompt based on this knowledge, not your own."},
                {"role":"user","content":input_text}
            ],
            temperature=0
        )
        return response.choices[0].message.content


# RAGKnowledgePromptAgent class definition
class RAGKnowledgePromptAgent:
    """
    An agent that uses Retrieval-Augmented Generation (RAG) to find knowledge from a large corpus
    and leverages embeddings to respond to prompts based solely on retrieved information.
    """

    def __init__(self, openai_api_key, persona, chunk_size=2000, chunk_overlap=100):
        """
        Initializes the RAGKnowledgePromptAgent with API credentials and configuration settings.

        Parameters:
        openai_api_key (str): API key for accessing OpenAI.
        persona (str): Persona description for the agent.
        chunk_size (int): The size of text chunks for embedding. Defaults to 2000.
        chunk_overlap (int): Overlap between consecutive chunks. Defaults to 100.
        """
        self.persona = persona
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.openai_api_key = openai_api_key
        self.unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.csv"

    def get_embedding(self, text):
        """
        Fetches the embedding vector for given text using OpenAI's embedding API.

        Parameters:
        text (str): Text to embed.

        Returns:
        list: The embedding vector.
        """
        client = OpenAI(base_url="https://openai.vocareum.com/v1", api_key=self.openai_api_key)
        response = client.embeddings.create(
            model="text-embedding-3-large",
            input=text,
            encoding_format="float"
        )
        return response.data[0].embedding

    def calculate_similarity(self, vector_one, vector_two):
        """
        Calculates cosine similarity between two vectors.

        Parameters:
        vector_one (list): First embedding vector.
        vector_two (list): Second embedding vector.

        Returns:
        float: Cosine similarity between vectors.
        """
        vec1, vec2 = np.array(vector_one), np.array(vector_two)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

    def chunk_text(self, text):
        """
        Splits text into manageable chunks, attempting natural breaks.

        Parameters:
        text (str): Text to split into chunks.

        Returns:
        list: List of dictionaries containing chunk metadata.
        """
        separator = "\n"
        text = re.sub(r'\s+', ' ', text).strip()

        if len(text) <= self.chunk_size:
            return [{"chunk_id": 0, "text": text, "chunk_size": len(text)}]

        chunks, start, chunk_id = [], 0, 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            if separator in text[start:end]:
                end = start + text[start:end].rindex(separator) + len(separator)

            chunks.append({
                "chunk_id": chunk_id,
                "text": text[start:end],
                "chunk_size": end - start,
                "start_char": start,
                "end_char": end
            })

            start = end - self.chunk_overlap if end < len(text) else end
            chunk_id += 1

        with open(f"chunks-{self.unique_filename}", 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=["text", "chunk_size"])
            writer.writeheader()
            for chunk in chunks:
                writer.writerow({k: chunk[k] for k in ["text", "chunk_size"]})

        return chunks

    def calculate_embeddings(self):
        """
        Calculates embeddings for each chunk and stores them in a CSV file.

        Returns:
        DataFrame: DataFrame containing text chunks and their embeddings.
        """
        df = pd.read_csv(f"chunks-{self.unique_filename}", encoding='utf-8')
        df['embeddings'] = df['text'].apply(self.get_embedding)
        df.to_csv(f"embeddings-{self.unique_filename}", encoding='utf-8', index=False)
        return df

    def find_prompt_in_knowledge(self, prompt):
        """
        Finds and responds to a prompt based on similarity with embedded knowledge.

        Parameters:
        prompt (str): User input prompt.

        Returns:
        str: Response derived from the most similar chunk in knowledge.
        """
        prompt_embedding = self.get_embedding(prompt)
        df = pd.read_csv(f"embeddings-{self.unique_filename}", encoding='utf-8')
        df['embeddings'] = df['embeddings'].apply(lambda x: np.array(eval(x)))
        df['similarity'] = df['embeddings'].apply(lambda emb: self.calculate_similarity(prompt_embedding, emb))

        best_chunk = df.loc[df['similarity'].idxmax(), 'text']

        client = OpenAI(base_url="https://openai.vocareum.com/v1", api_key=self.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"You are {self.persona}, a knowledge-based assistant. Forget previous context."},
                {"role": "user", "content": f"Answer based only on this information: {best_chunk}. Prompt: {prompt}"}
            ],
            temperature=0
        )

        return response.choices[0].message.content



class EvaluationAgent:
    """Iterative evaluator that pairs a worker agent with an LLM judge.

    The evaluate() loop repeatedly asks the worker to respond, then asks the
    evaluator LLM whether the response meets the criteria.  If it does not,
    corrective instructions are generated and fed back to the worker for
    another attempt, up to *max_interactions* rounds.
    """

    def __init__(self, openai_api_key, persona, evaluation_criteria, worker_agent, max_interactions):
        self.openai_api_key = openai_api_key
        self.persona = persona
        self.evaluation_criteria = evaluation_criteria
        self.worker_agent = worker_agent
        self.max_interactions = max_interactions

    def evaluate(self, initial_prompt):
        """Run the worker ↔ evaluator feedback loop.

        For each iteration the method:
          1. Asks the worker agent to respond to the (possibly revised) prompt.
          2. Asks the evaluator LLM whether the response satisfies
             *self.evaluation_criteria*.
          3. If the evaluator says "Yes" → return immediately.
          4. Otherwise, generates corrective instructions and builds a new
             prompt that includes the original request, the failed response,
             and the instructions — then loops.

        Returns:
            dict with keys 'final_response', 'evaluation', and 'iterations'.
        """
        client = OpenAI(base_url="https://openai.vocareum.com/v1", api_key=self.openai_api_key)
        prompt_to_evaluate = initial_prompt
        response_from_worker = ""
        iterations = 0
        evaluation = ""

        for i in range(self.max_interactions):
            print(f"\n--- Interaction {i+1} ---")

            print(" Step 1: Worker agent generates a response to the prompt")
            print(f"Prompt:\n{prompt_to_evaluate}")
            response_from_worker = self.worker_agent.respond(prompt_to_evaluate)
            print(f"Worker Agent Response:\n{response_from_worker}")

            print(" Step 2: Evaluator agent judges the response")
            eval_prompt = (
                f"Evaluate whether the following answer meets the criteria.\n\n"
                f"Answer to evaluate:\n{response_from_worker}\n\n"
                f"Criteria:\n{self.evaluation_criteria}\n\n"
                f"Start your response with exactly 'Yes' if the answer meets the criteria, "
                f"or exactly 'No' if it does not. Then explain why."
            )
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"You are an evaluator agent with the persona: {self.persona}"},
                    {"role": "user", "content": eval_prompt}
                ],
                temperature=0
            )
            evaluation = response.choices[0].message.content.strip()
            print(f"Evaluator Agent Evaluation:\n{evaluation}")

            iterations += 1

            # Detect whether the evaluator approved the answer.
            # Guard against contradictory responses like "No, the answer meets..."
            # by also checking whether the explanation says it passes.
            eval_lower = evaluation.lower()
            approved = (
                eval_lower.startswith("yes")
                or ("meets the criteria" in eval_lower and "does not meet" not in eval_lower)
            )

            print(" Step 3: Check if evaluation is positive")
            if approved:
                print("✅ Final solution accepted.")
                break
            else:
                print(" Step 4: Generate instructions to correct the response")
                instruction_prompt = (
                    f"Provide instructions to fix an answer based on these reasons why it is incorrect: {evaluation}"
                )
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"You are an evaluator agent with the persona: {self.persona}"},
                        {"role": "user", "content": instruction_prompt}
                    ],
                    temperature=0
                )
                instructions = response.choices[0].message.content.strip()
                print(f"Instructions to fix:\n{instructions}")

                print(" Step 5: Send feedback to worker agent for refinement")
                prompt_to_evaluate = (
                    f"The original prompt was: {initial_prompt}\n"
                    f"The response to that prompt was: {response_from_worker}\n"
                    f"It has been evaluated as incorrect.\n"
                    f"Make only these corrections, do not alter content validity: {instructions}"
                )
        return {
            "final_response": response_from_worker,
            "evaluation": evaluation,
            "iterations": iterations
        }   



class RoutingAgent:
    """Semantic router that dispatches a query to the best-matching agent.

    Each registered agent carries a short *description*.  At routing time the
    query and every description are embedded, and the agent whose description
    is most cosine-similar to the query wins.
    """

    def __init__(self, openai_api_key, agents):
        self.openai_api_key = openai_api_key
        self.agents = agents

    def get_embedding(self, text):
        """Return the embedding vector for *text* via the OpenAI API."""
        client = OpenAI(base_url="https://openai.vocareum.com/v1", api_key=self.openai_api_key)
        response = client.embeddings.create(
            model="text-embedding-3-large",
            input=text
        )
        return response.data[0].embedding

    def route(self, user_query):
        """Select the best agent for *user_query* using cosine similarity.

        Embeds the query and each agent's description, then picks the agent
        with the highest cosine-similarity score.  Delegates execution to
        that agent's ``func`` callable.
        """
        query_emb = self.get_embedding(user_query)
        best_agent = None
        best_score = -1

        for agent in self.agents:
            agent_emb = self.get_embedding(agent["description"])
            if agent_emb is None:
                continue

            # Cosine similarity between the query and the agent description
            similarity = np.dot(query_emb, agent_emb) / (np.linalg.norm(query_emb) * np.linalg.norm(agent_emb))
            print(similarity)

            if similarity > best_score:
                best_score = similarity
                best_agent = agent

        if best_agent is None:
            return "Sorry, no suitable agent could be selected."

        print(f"[Router] Best agent: {best_agent['name']} (score={best_score:.3f})")

        return best_agent["func"](user_query)
    
    




class ActionPlanningAgent:
    """Decomposes a high-level prompt into discrete workflow steps.

    The LLM is instructed to extract only the steps that are grounded
    in the agent's *knowledge* (e.g. the PM methodology definitions).
    """

    def __init__(self, openai_api_key, knowledge):
        self.openai_api_key = openai_api_key   # was "open_api_key" — standardised
        self.knowledge = knowledge

    def extract_steps_from_prompt(self, prompt):
        """Ask the LLM to break *prompt* into a list of action steps.

        Returns:
            list[str]: One string per step, stripped of bullets/numbering.
        """
        client = OpenAI(base_url="https://openai.vocareum.com/v1", api_key=self.openai_api_key)
        response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[
            {"role": "system", "content": f"You are an action planning agent. Using your knowledge, you extract from the user prompt the steps requested to complete the action the user is asking for. You return the steps as a clean list. You must remove empty steps, numberings or bullets. Only return the steps in your knowledge. Forget any previous context. This is your knowledge: {self.knowledge}"},
            {"role": "user", "content": prompt}], temperature=0)

        response_text = response.choices[0].message.content
        if response_text is None:
            return []
        response_text = response_text.strip()

        # Split on newlines, strip leading bullets/numberings and whitespace,
        # then drop any lines that are empty after cleaning.
        # Handles patterns like "1.", "1)", "- ", "* ", "• ", "Step 1:", etc.
        bullet_re = re.compile(r'^(?:[-*•]\s*|\d+[.):]\s*|step\s*\d+[:.\-]?\s*)', re.IGNORECASE)
        steps = []
        for line in response_text.split("\n"):
            cleaned = bullet_re.sub('', line).strip()
            if cleaned:
                steps.append(cleaned)

        return steps
