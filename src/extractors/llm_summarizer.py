"""
LLM-based page summarization and knowledge extraction
"""

import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import asyncio
from dataclasses import dataclass

# LLM provider imports
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

from ..models.schemas import Feature, Page, MemoryEntry

logger = logging.getLogger(__name__)


@dataclass
class SummarizationPrompt:
    """Structured prompt for summarization"""
    system: str
    user: str


class LLMSummarizer:
    """
    Base class for LLM-based page summarization
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.provider = config.get("llm_provider", "openai")
        self.model = config.get("llm_model", "gpt-4-turbo-preview")
        self.max_tokens = config.get("max_tokens", 500)
        self.temperature = config.get("temperature", 0.3)

        # Initialize LLM client
        self._init_llm_client()

    def _init_llm_client(self):
        """Initialize the LLM client based on provider"""
        if self.provider == "openai" and HAS_OPENAI:
            openai.api_key = os.getenv("OPENAI_API_KEY")
            self.client = openai
        elif self.provider == "anthropic" and HAS_ANTHROPIC:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            self.client = anthropic.Anthropic(api_key=api_key)
        else:
            raise ValueError(f"LLM provider {self.provider} not available or not supported")

    async def summarize_page(
        self,
        page_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Summarize a single page

        Args:
            page_data: Raw page data from crawler
            context: Additional context (client info, role, etc.)

        Returns:
            Structured summary
        """
        prompt = self._create_page_prompt(page_data, context)
        response = await self._call_llm(prompt)
        return self._parse_response(response)

    def _create_page_prompt(
        self,
        page_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> SummarizationPrompt:
        """Create prompt for page summarization"""

        # Extract key information from page data
        url = page_data.get("url", "")
        title = page_data.get("metadata", {}).get("title", "")
        main_text = page_data.get("content", {}).get("main_text", "")[:2000]  # Limit text
        components = page_data.get("components", [])
        navigation = page_data.get("navigation", {})
        headings = page_data.get("headings", [])

        system_prompt = """You are an expert at analyzing web pages for a Website Intelligence Platform.
Your task is to extract structured information that will help an AI agent understand and navigate the website.
Focus on:
1. The primary purpose of the page
2. Key actions a user can perform
3. Navigation paths to reach this page
4. Important UI components and their functions
5. Any forms, inputs, or interactive elements

Return your analysis as a structured JSON object."""

        user_prompt = f"""Analyze this page from a solar asset management platform:

URL: {url}
Title: {title}

NAVIGATION STRUCTURE:
{json.dumps(navigation, indent=2)[:500]}

PAGE HEADINGS:
{json.dumps(headings, indent=2)[:300]}

UI COMPONENTS:
{json.dumps(components[:5], indent=2)[:500]}

MAIN CONTENT (excerpt):
{main_text}

"""

        if context:
            user_prompt += f"""
CLIENT CONTEXT:
- Client Type: {context.get('client_type', 'enterprise')}
- Asset Types: {context.get('asset_types', [])}
- User Role: {context.get('role', 'admin')}
"""

        user_prompt += """
Please provide a JSON response with:
{
  "purpose": "one sentence describing the page's main purpose",
  "key_actions": ["list of main actions users can perform"],
  "navigation_path": "how to reach this page from the main menu",
  "important_elements": [
    {
      "name": "element name",
      "type": "button/form/table/chart",
      "function": "what it does"
    }
  ],
  "user_instructions": "clear instructions on how to use this page",
  "data_displayed": ["types of data shown on this page"],
  "related_features": ["related features or pages"]
}
"""

        return SummarizationPrompt(system=system_prompt, user=user_prompt)

    async def _call_llm(self, prompt: SummarizationPrompt) -> str:
        """Call the LLM API"""
        if self.provider == "openai":
            return await self._call_openai(prompt)
        elif self.provider == "anthropic":
            return await self._call_anthropic(prompt)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    async def _call_openai(self, prompt: SummarizationPrompt) -> str:
        """Call OpenAI API"""
        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return "{}"

    async def _call_anthropic(self, prompt: SummarizationPrompt) -> str:
        """Call Anthropic API"""
        try:
            message = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=prompt.system,
                messages=[
                    {"role": "user", "content": prompt.user}
                ]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            return "{}"

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response: {response[:100]}...")
            return {
                "purpose": "Unable to determine page purpose",
                "key_actions": [],
                "error": "Failed to parse LLM response"
            }


class FeatureSummarizer(LLMSummarizer):
    """
    Specialized summarizer for feature-level documentation
    """

    async def summarize_feature(
        self,
        feature_pages: List[Dict[str, Any]],
        feature_info: Feature
    ) -> Dict[str, Any]:
        """
        Summarize an entire feature based on its pages

        Args:
            feature_pages: All pages belonging to this feature
            feature_info: Feature metadata

        Returns:
            Comprehensive feature summary
        """
        prompt = self._create_feature_prompt(feature_pages, feature_info)
        response = await self._call_llm(prompt)
        return self._parse_response(response)

    def _create_feature_prompt(
        self,
        pages: List[Dict[str, Any]],
        feature: Feature
    ) -> SummarizationPrompt:
        """Create prompt for feature summarization"""

        system_prompt = """You are documenting features for a solar asset management platform.
Create comprehensive documentation that helps AI agents understand the complete functionality of each feature.
Focus on user workflows, capabilities, and navigation patterns."""

        # Aggregate information from all pages
        page_summaries = []
        for page in pages[:5]:  # Limit to prevent token overflow
            page_summaries.append({
                "url": page.get("url", ""),
                "title": page.get("metadata", {}).get("title", ""),
                "components": [c.get("name") for c in page.get("components", [])[:3]]
            })

        user_prompt = f"""Document this feature comprehensively:

FEATURE: {feature.name}
DESCRIPTION: {feature.description}
CATEGORY: {feature.category}

PAGES IN THIS FEATURE:
{json.dumps(page_summaries, indent=2)}

KEY ACTIONS AVAILABLE:
{json.dumps(feature.key_actions, indent=2)}

Create a JSON response with:
{{
  "overview": "2-3 sentence overview of the feature",
  "user_workflows": [
    {{
      "name": "workflow name",
      "steps": ["step 1", "step 2", "..."],
      "outcome": "what is achieved"
    }}
  ],
  "navigation_instructions": "how to access and navigate this feature",
  "key_capabilities": ["main things users can do"],
  "data_managed": ["types of data this feature handles"],
  "common_tasks": [
    {{
      "task": "task description",
      "instructions": "step-by-step instructions"
    }}
  ],
  "related_features": ["features that work with this one"],
  "permissions_required": ["roles or permissions needed"]
}}
"""

        return SummarizationPrompt(system=system_prompt, user=user_prompt)


class MemoryGenerator:
    """
    Generates memory entries for the vector store
    """

    def __init__(self, summarizer: LLMSummarizer):
        self.summarizer = summarizer

    async def generate_memory_entry(
        self,
        page_summary: Dict[str, Any],
        page_data: Dict[str, Any],
        client_context: Optional[Dict[str, Any]] = None
    ) -> MemoryEntry:
        """
        Generate a memory entry from page summary

        Args:
            page_summary: LLM-generated summary
            page_data: Original page data
            client_context: Client and role information

        Returns:
            MemoryEntry ready for vector store
        """
        # Create the memory text
        memory_text = self._create_memory_text(page_summary, client_context)

        # Create metadata
        metadata = {
            "client_id": client_context.get("client_id", "global") if client_context else "global",
            "role_id": client_context.get("role_id") if client_context else None,
            "feature_id": page_data.get("feature_id"),
            "page_id": page_data.get("page_id"),
            "label": page_summary.get("purpose", ""),
            "canonical_name": page_data.get("metadata", {}).get("title", ""),
            "url": page_data.get("url", ""),
            "nav_path": page_summary.get("navigation_path", ""),
            "tags": self._extract_tags(page_summary),
            "priority": self._calculate_priority(page_summary),
            "version": 1,
            "last_updated": datetime.utcnow()
        }

        return MemoryEntry(
            memory_id=self._generate_memory_id(metadata),
            text=memory_text,
            metadata=metadata,
            confidence_score=self._calculate_confidence(page_summary)
        )

    def _create_memory_text(
        self,
        summary: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create natural language memory text"""
        parts = []

        # Main purpose
        parts.append(f"Page Purpose: {summary.get('purpose', '')}")

        # Navigation
        nav_path = summary.get('navigation_path', '')
        if nav_path:
            parts.append(f"To access this page: {nav_path}")

        # User instructions
        instructions = summary.get('user_instructions', '')
        if instructions:
            parts.append(f"How to use: {instructions}")

        # Key actions
        actions = summary.get('key_actions', [])
        if actions:
            parts.append(f"Available actions: {', '.join(actions)}")

        # Context-specific information
        if context:
            if context.get('label_override'):
                parts.append(f"This feature is labeled as '{context['label_override']}' for your organization.")

            if context.get('role_restrictions'):
                parts.append(f"Access restrictions: {context['role_restrictions']}")

        return " ".join(parts)

    def _extract_tags(self, summary: Dict[str, Any]) -> List[str]:
        """Extract searchable tags from summary"""
        tags = []

        # Add tags from key actions
        for action in summary.get('key_actions', []):
            tags.extend(action.lower().split())

        # Add tags from data types
        for data_type in summary.get('data_displayed', []):
            tags.append(data_type.lower())

        # Add tags from related features
        tags.extend(summary.get('related_features', []))

        # Deduplicate and clean
        tags = list(set(tag for tag in tags if len(tag) > 2))

        return tags[:10]  # Limit number of tags

    def _calculate_priority(self, summary: Dict[str, Any]) -> str:
        """Calculate priority based on page importance"""
        # High priority if it has many actions or is a dashboard
        key_actions = summary.get('key_actions', [])
        purpose = summary.get('purpose', '').lower()

        if 'dashboard' in purpose or 'overview' in purpose:
            return "high"
        elif len(key_actions) > 5:
            return "high"
        elif len(key_actions) > 2:
            return "medium"
        else:
            return "low"

    def _calculate_confidence(self, summary: Dict[str, Any]) -> float:
        """Calculate confidence score for the summary"""
        # Base confidence
        confidence = 0.8

        # Increase if we have complete information
        if summary.get('purpose'):
            confidence += 0.05
        if summary.get('key_actions'):
            confidence += 0.05
        if summary.get('navigation_path'):
            confidence += 0.05
        if not summary.get('error'):
            confidence += 0.05

        return min(1.0, confidence)

    def _generate_memory_id(self, metadata: Dict[str, Any]) -> str:
        """Generate unique memory ID"""
        import hashlib

        # Create ID from client, role, and page
        components = [
            metadata.get("client_id", ""),
            metadata.get("role_id", ""),
            metadata.get("page_id", ""),
            metadata.get("url", "")
        ]

        id_string = "_".join(filter(None, components))
        return hashlib.sha256(id_string.encode()).hexdigest()[:16]


class BatchSummarizer:
    """
    Handles batch summarization of multiple pages
    """

    def __init__(self, summarizer: LLMSummarizer, batch_size: int = 5):
        self.summarizer = summarizer
        self.batch_size = batch_size
        self.semaphore = asyncio.Semaphore(batch_size)

    async def summarize_batch(
        self,
        pages: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Summarize multiple pages concurrently"""
        tasks = []

        for page in pages:
            task = self._summarize_with_limit(page, context)
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        summaries = []
        for page, result in zip(pages, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to summarize page {page.get('url', '')}: {result}")
                summaries.append({"error": str(result)})
            else:
                summaries.append(result)

        return summaries

    async def _summarize_with_limit(
        self,
        page: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Summarize with concurrency limit"""
        async with self.semaphore:
            return await self.summarizer.summarize_page(page, context)