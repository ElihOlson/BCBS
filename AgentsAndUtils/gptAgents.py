from groq import Groq
import os
from supabase import *
import json
from dotenv import load_dotenv
from pathlib import Path

basedir = Path(__file__).resolve().parent
load_dotenv(basedir / ".env")


grokKey = os.getenv("GROK_API_KEY")
spbsKey = os.getenv("SUPABASE_KEY2")
spbsUrl = os.getenv("SUPABASE_URL2")


#get emails out
#fix sql execution


class sqlAgent:
    def __init__(self):
        
        

        self.client = Groq(api_key=grokKey)

        self.SUPABASE_URL = spbsUrl
        self.SUPABASE_KEY = spbsKey

        DBClient = create_client(self.SUPABASE_URL, self.SUPABASE_KEY)



    def genSQL(self, prompt, schema):
        # Single call: return SQL or "INVALID" — avoids sending schema twice
        sysPrompt = (
            f"Schema:{schema}\n"
            "Return a SQL query for the user request. Add (marketing_ai.) before all column names i.e. SELECT m.* FROM marketing_ai.members m"
            "If the request cannot be answered from the schema, reply only: INVALID"
        )
        result = self.sendMessage(prompt, sysPrompt)
        if result.strip().upper() == "INVALID":
            return "Bad Request"
        return result




    def sendMessage(self, prompt, systemPrompt):
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": systemPrompt},
                {"role": "user", "content": prompt},
            ],
            model="llama-3.1-8b-instant",
            # max_tokens=500,
        )
        return chat_completion.choices[0].message.content


    def readDB(self,dbInfo):


        #format llm output into a dict
        colsList = self.formatter(dbInfo)
        #print(f"COL LIST: {colsList}")

        colString = ""

        for x in range(len(colsList)):
            if x == 0:
                colString = colsList[x]
            else:
                colString = colString + ", " + colsList[x]
        #print(f"COLSTRING: {colString}")

        response = self.DBClient.table("Test1").select(colString).execute()

        data = response.data
        #print(data)
        self.printer(data)

    #take llm json and turn it into usable struct
    def formatter(self,json_string):
        
        #check if string can be formatted

        # Convert string to a Python dictionary
        data = json.loads(json_string)

        return data['columns']

    def printer(self,data,limit = 20):
        
        
        if not data:
            print("No data")
            return

        total_rows = len(data)
        rows = data[:limit]

        # Use consistent column order (from first row)
        columns = list(data[0].keys())

        # Compute column widths (only from displayed rows)
        col_widths = {
            col: max(
                len(col),
                max(len(str(row.get(col, ""))) for row in rows)
            )
            for col in columns
        }

        # Header
        header = " | ".join(col.ljust(col_widths[col]) for col in columns)
        print(header)
        print("-" * len(header))

        # Rows
        for row in rows:
            print(" | ".join(str(row.get(col, "")).ljust(col_widths[col]) for col in columns))

        # Footer info
        if total_rows > limit:
            print(f"\nShowing {limit} of {total_rows} rows...")
        else:
            print(f"\nTotal rows: {total_rows}")
#=====================================================================================#
#==================================End of Functions===================================#
#=====================================================================================#


class bucketingAgent:
    def __init__(self,):

        self.client = Groq(api_key=grokKey)
        self.SUPABASE_URL = spbsUrl
        self.SUPABASE_KEY = spbsKey
        DBClient = create_client(self.SUPABASE_URL, self.SUPABASE_KEY)

        #self.schema = r"TABLE: users\nCOLUMNS: id,first_name,last_name,email,phone,city,state"

    def sendMessage(self, prompt='none', systemPrompt='none'):
        chat_completion = self.client.chat.completions.create(
            messages=[
                {"role": "system", "content": systemPrompt},
                {"role": "user", "content": prompt},
            ],
            model="llama-3.1-8b-instant",
            # max_tokens=500,
        )
        return chat_completion.choices[0].message.content
    
    def generateBuckets(self,sqlQuery,schema):
        
        #create bucket ideas given schema
        #return sql queries for each bucket
        #sqlQuery = "SELECT first_name, email FROM users WHERE LOWER(first_name) = 'joe';"
        #schema = "TABLE: users\nCOLUMNS: id,first_name,last_name,email,phone,city,state"

        if isinstance(schema, list):
            schemaText = "\n".join(str(line) for line in schema)
        else:
            schemaText = str(schema)

        systemPrompt = (
            r""" ROLE
                        You are a member-segmentation agent for a healthcare engagement platform. Your job is to take a campaign brief and produce an *outreach strategy* — a small set of mutually exclusive member buckets, each with its own SQL, count, and rationale for why that bucket deserves its own treatment.

                        You are NOT being asked for a single SELECT. You are being asked to decompose a target population into the buckets that a marketing analyst should treat differently to maximize the weighted success metric.

                        SCHEMA

                        Use ONLY the schema below. Every query must be qualified with `marketing_ai.` (this is non-negotiable).

                        """
            + schemaText +
            r"""

                        Notes on the schema you MUST respect:
                        - Conditions are in `member_conditions` (joined by member_id, with icd10_code). Do not invent a `member_features` table.
                        - State/location comes through `members -> addresses` (addresses.state).
                        - Age must be computed from `members.date_of_birth` against CURRENT_DATE.
                        - SMS opt-in lives in `consent_preferences.sms_opt_in`. Required for every bucket.
                        - Active suppression lives in `suppression_lists` where channel = 'sms' and (expires_at IS NULL OR expires_at > CURRENT_DATE). Required exclusion for every bucket.
                        - SMS engagement history lives in `sms_events` (event_type values include 'delivered', 'clicked', 'replied', 'opt_out', etc.).
                        - Member must be currently active: `members.status = 'ACTIVE'` AND they have an active `enrollments` row where `is_active = TRUE`.

                        INPUT BRIEF

                        User request: { "about": { "age_range": [25, 40], "location": ["NE", "IA"], "conditions": ["diabetes", "hypertension"], "engagement_level": "medium" }, "for": { "campaign_type": "preventive_care", "channel": "sms", "message_goal": "schedule_appointment" }, "success_conditions": { "primary_metric": "conversion_rate", "secondary_metrics": ["open_rate", "click_rate"], "weights": { "conversion_rate": 0.6, "open_rate": 0.25, "click_rate": 0.15 } } }

                        The brief has three parts:
                        - `about` — describes the TARGET UNIVERSE. Treat this as a hard filter: every bucket must be a subset of this universe.
                        - `for` — describes the CAMPAIGN. Use this to pick which dimensions to slice the universe by. Different campaign_type / channel / message_goal combinations imply different slicing.
                        - `success_conditions` — describes HOW TO SCORE a bucketing strategy. Use the weights to decide which dimensions matter most:
                            - High `conversion_rate` weight → slice by signals that predict action-taking (care_gaps status, propensity_scores, prior appointment-related NBA actions).
                            - High `open_rate` weight → slice by recency/frequency of inbound engagement (sms_events, portal_events, app_logins).
                            - High `click_rate` weight → slice by prior SMS click behavior and preferred time-of-day/day-of-week.

                        WHAT TO PRODUCE

                        Produce **4 to 7 buckets**. Each bucket must:
                        1. Be a strict subset of the target universe defined by `about`.
                        2. Be *mutually exclusive* from the other buckets on the dimension that most drives the primary success metric.
                        3. Exclude suppressed members and require SMS opt-in (always).
                        4. Only exist if it deserves a *different outreach treatment* than every other bucket. If two candidate buckets would get the same SMS, merge them.

                        For each bucket, return these fields (see OUTPUT FORMAT):
                        - `rank` — 1-indexed, ordered by which bucket the analyst should prioritize given the success weights.
                        - `name` — short, descriptive, human-readable (e.g., "Engaged clickers, overdue on A1C").
                        - `sql` — a complete SELECT against `marketing_ai.` qualified tables, returning member-level columns only (member_id, first_name, last_name, phone_mobile, plus any feature columns that support the rationale). Must include the universal guards: sms_opt_in = TRUE, not in active sms suppressions, members.status = 'ACTIVE', active enrollment. Use AND-only conditions as required.
                        - `estimated_count` — INTEGER. Your best estimate. If you cannot compute a real count, return a SQL comment at the top of the query with `/* estimated_count: <reasoning> */` and set the field to null — never fabricate.
                        - `rationale` — 2–4 sentences. Must cover: (a) WHY this slice exists as its own bucket, (b) which success metric(s) it's optimized for and how, (c) what differentiated message or timing this bucket implies.
                        - `suggested_treatment` — 1 sentence on what the SMS for this bucket should emphasize (e.g., "Lead with a one-tap scheduling link; send Tue–Thu 10a–12p based on prior click time-of-day.").

                        SLICING HEURISTIC (follow this — it's what's been missing)

                        Given the brief's weights (conversion 0.6 / open 0.25 / click 0.15), your dominant slicing axis should be **behavioral signals that predict conversion**, not demographics. Candidate dimensions, in rough priority order for THIS brief:

                        1. **Open care gap for a preventive measure** (`care_gaps.status = 'OPEN'`, measure_category relevant to preventive/diabetes/hypertension). Members with an open gap are structurally more convertible.
                        2. **Prior SMS engagement tier** — join `sms_events` for the last 180 days and tier members: clicked-at-least-once / opened-but-no-click / delivered-no-interaction / no-recent-sms. This slices both open_rate and click_rate behavior.
                        3. **Propensity score decile** from `propensity_scores` if a relevant `model_name` exists (filter to the latest `computed_at` per member).
                        4. **Next-best-action already queued** (`next_best_actions` with action_type related to scheduling/appointments and status = 'PENDING') — these members have an open recommendation and should probably be treated as a distinct bucket.
                        5. **Channel-preference conflict** — members whose `consent_preferences.preferred_channel` is NOT sms but sms_opt_in is still TRUE are a weaker bucket; split them.

                        Do NOT slice primarily by age bracket, state, or condition subtype within the universe — those are already fixed by `about`. Slicing on them further produces buckets that don't deserve different treatment.

                        HARD RULES

                        - Only SELECT statements. No DDL, DML, or side effects.
                        - Only AND in WHERE clauses (as specified by the platform).
                        - Every table reference qualified with `marketing_ai.`.
                        - Every bucket's SQL must include the universal guards (opt-in, no suppression, active member, active enrollment).
                        - Return member-level rows only. No aggregates in the bucket SQL itself — the aggregate (count) goes in `estimated_count`.
                        - If the brief's universe or the schema makes a given slicing dimension unusable, drop it silently and pick the next one — don't explain what you didn't do.

                        OUTPUT FORMAT

                        Return a single JSON object, nothing else. No prose before or after. Shape:

                        {
                        "universe_definition": "<one sentence describing the hard filter set by `about`>",
                        "primary_slicing_axis": "<one phrase naming the dominant dimension you sliced on and why, referencing the weights>",
                        "buckets": [
                            {
                            "rank": 1,
                            "name": "...",
                            "sql": "SELECT ...",
                            "estimated_count": 1234,
                            "rationale": "...",
                            "suggested_treatment": "..."
                        remove all formatting from the SQL(VERY IMPORTANT!!!)
                            },
                            ...
                        ],
                        "coverage_note": "<one sentence on what fraction of the universe is covered by the bucket set and whether any meaningful sub-population is intentionally excluded>"
                        }"""
        )

        return self.sendMessage(sqlQuery,systemPrompt)


    def userPromptedBuckets():
        pass
