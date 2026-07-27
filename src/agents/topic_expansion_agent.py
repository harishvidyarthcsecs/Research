"""
Topic Expansion Agent - Decomposes research topics into subtopics and research directions.

Primary mode ("llm"): asks the shared LLM client to decompose the topic into
subtopics, methods, datasets, related areas and search keywords, so expansion
generalizes beyond a fixed set of domains.

Fallback mode ("rules"): the original hardcoded 5-domain keyword dictionary,
kept as the no-API-key fallback and rule-based ablation baseline
(set TOPIC_MODE=rules), mirroring CONTRADICTION_MODE / GAP_MODE.
"""
from typing import List, Dict, Any, Optional
import json
import os
import re
from ..models.data_models import TopicMap
from .base_agent import BaseAgent
from . import llm_client


class TopicExpansionAgent(BaseAgent):
    """Agent responsible for expanding research topics into structured maps."""

    def __init__(self, memory_store=None, mode: Optional[str] = None):
        super().__init__("TopicExpansionAgent", memory_store)
        self.mode = mode  # None = auto: "llm" if a provider is available
        self.tracker: Optional[llm_client.UsageTracker] = None
        self.domain_keywords = self._load_domain_keywords()

    def _resolve_mode(self) -> str:
        mode = self.mode or os.getenv("TOPIC_MODE")
        if mode in ("llm", "rules"):
            return mode
        return "llm" if llm_client.get_provider() is not None else "rules"
    
    def _load_domain_keywords(self) -> Dict[str, List[str]]:
        """Load domain-specific keywords for topic expansion."""
        return {
            "machine_learning": [
                "neural networks", "deep learning", "supervised learning", 
                "unsupervised learning", "reinforcement learning", "transfer learning"
            ],
            "drug_discovery": [
                "molecular design", "pharmacokinetics", "drug screening", 
                "target identification", "lead optimization", "clinical trials"
            ],
            "graph_neural_networks": [
                "graph convolution", "message passing", "graph attention", 
                "graph pooling", "node classification", "link prediction"
            ],
            "computer_vision": [
                "image classification", "object detection", "segmentation", 
                "feature extraction", "convolutional networks"
            ],
            "natural_language_processing": [
                "text classification", "named entity recognition", "sentiment analysis", 
                "language modeling", "machine translation"
            ]
        }
    
    async def process(self, topic: str) -> TopicMap:
        """
        Expand a research topic into a structured topic map.
        
        Args:
            topic: Main research topic string
            
        Returns:
            TopicMap: Structured representation of the topic
        """
        mode = self._resolve_mode()
        self.log_operation("topic_expansion_start", {"topic": topic, "mode": mode})

        main_topic = topic.strip()
        topic_map = None

        if mode == "llm":
            topic_map = self._llm_expand(main_topic)
            if topic_map is None:
                mode = "rules"

        if topic_map is None:
            topic_map = TopicMap(
                main_topic=main_topic,
                subtopics=self._extract_subtopics(topic),
                methods=self._extract_methods(topic),
                datasets=self._extract_datasets(topic),
                related_areas=self._extract_related_areas(topic),
                keywords=self._extract_keywords(topic),
            )

        # Store in memory for other agents
        await self.store_result("topic_map", topic_map)

        self.log_operation("topic_expansion_complete", {
            "mode": mode,
            "subtopics_count": len(topic_map.subtopics),
            "methods_count": len(topic_map.methods),
            "keywords_count": len(topic_map.keywords),
        })

        return topic_map

    # ------------------------------------------------------------------ #
    # LLM-based expansion (primary)                                      #
    # ------------------------------------------------------------------ #

    def _llm_expand(self, main_topic: str) -> Optional[TopicMap]:
        prompt = (
            "Decompose the following research topic into a structured map for "
            "literature search. Return ONLY a JSON object with keys:\n"
            "  subtopics (list of 3-6 specific subtopics or research directions), "
            "methods (list of 2-6 relevant methods/techniques), "
            "datasets (list of 0-6 commonly used benchmark datasets, empty if "
            "none are standard for this topic), "
            "related_areas (list of 2-5 related research areas), "
            "keywords (list of 6-12 search keywords/phrases for finding papers).\n"
            "Do not invent dataset names if you are not confident they exist.\n\n"
            f"Topic: {main_topic}"
        )
        try:
            raw = llm_client.chat(
                prompt,
                max_tokens=1024,
                temperature=0.0,
                tracker=self.tracker,
                purpose="topic_expansion",
            ).strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            data = json.loads(raw)
            return TopicMap(
                main_topic=main_topic,
                subtopics=[str(s) for s in data.get("subtopics", [])][:6],
                methods=[str(s) for s in data.get("methods", [])][:6],
                datasets=[str(s) for s in data.get("datasets", [])][:6],
                related_areas=[str(s) for s in data.get("related_areas", [])][:5],
                keywords=[str(s) for s in data.get("keywords", [])][:12],
            )
        except json.JSONDecodeError as e:
            if self.tracker is not None:
                self.tracker.record_parse_failure("topic_expansion")
            self.logger.warning(f"LLM topic expansion failed: {e}; falling back to rules")
            return None
        except Exception as e:
            self.logger.warning(f"LLM topic expansion failed: {e}; falling back to rules")
            return None
    
    def _extract_subtopics(self, topic: str) -> List[str]:
        """Extract potential subtopics from the main topic."""
        subtopics = []
        topic_lower = topic.lower()
        
        # Domain-specific subtopic extraction
        if "graph neural network" in topic_lower or "gnn" in topic_lower:
            subtopics.extend([
                "Graph Convolutional Networks",
                "Graph Attention Networks", 
                "Message Passing Neural Networks",
                "Graph Transformer Networks",
                "Spectral Graph Networks"
            ])
        
        if "drug discovery" in topic_lower:
            subtopics.extend([
                "Molecular Property Prediction",
                "Drug-Target Interaction",
                "Molecular Generation",
                "ADMET Prediction",
                "Virtual Screening"
            ])
        
        if "computer vision" in topic_lower:
            subtopics.extend([
                "Image Classification",
                "Object Detection",
                "Semantic Segmentation",
                "Instance Segmentation",
                "Image Generation"
            ])
        
        # Generic subtopic patterns
        if "classification" in topic_lower:
            subtopics.append("Multi-class Classification")
            subtopics.append("Binary Classification")
        
        if "prediction" in topic_lower:
            subtopics.append("Regression Analysis")
            subtopics.append("Time Series Prediction")
        
        return list(set(subtopics))
    
    def _extract_methods(self, topic: str) -> List[str]:
        """Extract relevant methods and techniques."""
        methods = []
        topic_lower = topic.lower()
        
        # Method extraction based on keywords
        method_patterns = {
            "neural": ["Neural Networks", "Deep Learning"],
            "graph": ["Graph Theory", "Network Analysis"],
            "machine learning": ["Supervised Learning", "Unsupervised Learning"],
            "optimization": ["Gradient Descent", "Evolutionary Algorithms"],
            "statistical": ["Statistical Analysis", "Bayesian Methods"]
        }
        
        for pattern, method_list in method_patterns.items():
            if pattern in topic_lower:
                methods.extend(method_list)
        
        return list(set(methods))
    
    def _extract_datasets(self, topic: str) -> List[str]:
        """Extract commonly used datasets for the topic."""
        datasets = []
        topic_lower = topic.lower()
        
        # Domain-specific datasets
        dataset_mapping = {
            "drug discovery": ["ChEMBL", "PubChem", "DrugBank", "ZINC", "QM9"],
            "computer vision": ["ImageNet", "COCO", "CIFAR-10", "MNIST", "Pascal VOC"],
            "natural language": ["GLUE", "SQuAD", "CoNLL", "WikiText", "Common Crawl"],
            "graph": ["Cora", "CiteSeer", "PubMed", "Reddit", "OGB"]
        }
        
        for domain, dataset_list in dataset_mapping.items():
            if any(keyword in topic_lower for keyword in domain.split()):
                datasets.extend(dataset_list)
        
        return list(set(datasets))
    
    def _extract_related_areas(self, topic: str) -> List[str]:
        """Extract related research areas."""
        related_areas = []
        topic_lower = topic.lower()
        
        # Cross-domain relationships
        if "drug discovery" in topic_lower:
            related_areas.extend([
                "Computational Chemistry",
                "Bioinformatics", 
                "Pharmacology",
                "Molecular Biology"
            ])
        
        if "graph neural" in topic_lower:
            related_areas.extend([
                "Network Science",
                "Social Network Analysis",
                "Knowledge Graphs",
                "Recommender Systems"
            ])
        
        if "machine learning" in topic_lower:
            related_areas.extend([
                "Artificial Intelligence",
                "Data Mining",
                "Pattern Recognition",
                "Statistical Learning"
            ])
        
        return list(set(related_areas))
    
    def _extract_keywords(self, topic: str) -> List[str]:
        """Extract relevant keywords for literature search."""
        keywords = []
        topic_lower = topic.lower()
        
        # Extract words from topic
        words = re.findall(r'\b\w+\b', topic_lower)
        keywords.extend(words)
        
        # Add domain-specific keywords
        for domain, keyword_list in self.domain_keywords.items():
            if any(word in topic_lower for word in domain.split('_')):
                keywords.extend(keyword_list)
        
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'use', 'using'}
        keywords = [kw for kw in keywords if kw not in stop_words and len(kw) > 2]
        
        return list(set(keywords))