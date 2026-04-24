print("hello")

def sendMessage(self, prompt, systemPrompt):

        outreach_strategy_schema = {
            "name": "generate_outreach_strategy",
            "description": "Generate a member segmentation outreach strategy with ranked buckets, SQL, and rationale.",
            "parameters": {
                "type": "object",
                "properties": {
                    "universe_definition": {
                        "type": "string",
                        "description": "Definition of the target population"
                    },
                    "primary_slicing_axis": {
                        "type": "string",
                        "description": "Main logic used to segment members"
                    },
                    "buckets": {
                        "type": "array",
                        "description": "List of mutually exclusive member buckets",
                        "items": {
                            "type": "object",
                            "properties": {
                                "rank": {
                                    "type": "integer",
                                    "description": "Priority rank of the bucket"
                                },
                                "name": {
                                    "type": "string",
                                    "description": "Bucket name"
                                },
                                "sql": {
                                    "type": "string",
                                    "description": "SQL query defining this bucket"
                                },
                                "estimated_count": {
                                    "type": ["integer", "null"],
                                    "description": "Estimated number of members in the bucket"
                                },
                                "rationale": {
                                    "type": "string",
                                    "description": "Why this bucket exists and why it matters"
                                },
                                "suggested_treatment": {
                                    "type": "string",
                                    "description": "Recommended outreach strategy"
                                }
                            },
                            "required": [
                                "rank",
                                "name",
                                "sql",
                                "estimated_count",
                                "rationale",
                                "suggested_treatment"
                            ]
                        }
                    },
                    "coverage_note": {
                        "type": "string",
                        "description": "Explanation of how much of the universe is covered"
                    }
                },
                "required": [
                    "universe_definition",
                    "primary_slicing_axis",
                    "buckets",
                    "coverage_note"
                ]
            }
        }

        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": systemPrompt},
                {"role": "user", "content": prompt}],
            tools=[{
                "type": "function",
                "function": outreach_strategy_schema
                }],
            tool_choice={
                "type": "function", "function": {"name": "generate_outreach_strategy"
                }},
            model="codestral-latest",
            # max_tokens=500,
        )
        return chat_completion.choices[0].message.content
        