"""Regression test for the narrative gate being measurable.

Background: for a stretch the eval harness reported
``downstream_errors.narrative_total_sentences == 0`` on every run, which made the
verify-or-reject vs scored-grounding comparison on narrative sentences
impossible. The causes were external (a dead LLM model id, an abstract-poor
frozen corpus) rather than a defect in the narrative path, but nothing pinned
the healthy behaviour down. This test does: on a small corpus whose papers carry
real abstracts and whose claims carry metrics/datasets, ``LiteratureBuilderAgent``
must emit at least one verified ``NarrativeSentence`` under ``grounding_mode="reject"``
with no LLM provider available (pure rules path).
"""
from unittest.mock import patch

import pytest

from src.agents import llm_client
from src.agents.literature_builder_agent import LiteratureBuilderAgent
from src.agents.paper_ids import paper_id_for
from src.models.data_models import Claim, PaperMetadata, ResearchResults, TopicMap


def _synthetic_corpus():
    papers = [
        PaperMetadata(
            title="Graph Convolutional Networks for Molecular Property Prediction",
            authors=["Alice Adams", "Bob Brown"], year=2021, venue="J. Chem. Inf.",
            doi="10.1000/gcn.mol.2021",
            abstract=(
                "We present a graph convolutional network for molecular property "
                "prediction. The method improves accuracy by 12% on the ChEMBL "
                "dataset compared to fingerprint baselines. A key limitation is the "
                "reliance on large labelled datasets."
            ),
        ),
        PaperMetadata(
            title="Message Passing Neural Networks for Drug-Target Interaction",
            authors=["Carol Clark", "Dan Davis"], year=2022, venue="Bioinformatics",
            doi="10.1000/mpnn.dti.2022",
            abstract=(
                "This work applies message passing neural networks to drug-target "
                "interaction. The model achieves an AUC of 0.91 on the BindingDB "
                "benchmark, outperforming prior methods. Performance degrades on "
                "unseen protein families."
            ),
        ),
    ]
    claims = [
        Claim(
            statement="A graph convolutional network improves accuracy by 12% on the ChEMBL dataset.",
            paper_id=paper_id_for(papers[0]), confidence=0.9,
            metrics={"accuracy": "+12%"}, datasets=["ChEMBL"],
        ),
        Claim(
            statement="A message passing neural network achieves an AUC of 0.91 on the BindingDB benchmark.",
            paper_id=paper_id_for(papers[1]), confidence=0.9,
            metrics={"AUC": "0.91"}, datasets=["BindingDB"],
        ),
    ]
    topic_map = TopicMap(
        main_topic="graph neural networks for drug discovery",
        subtopics=["molecular property prediction", "drug-target interaction"],
        methods=["graph convolutional network", "message passing neural network"],
        datasets=["ChEMBL", "BindingDB"],
        keywords=["GNN", "drug discovery", "molecular"],
    )
    return ResearchResults(
        topic_map=topic_map, papers=papers, claims=claims,
        contradictions=[], research_gaps=[], citations=[],
        total_papers_analyzed=2, total_claims_extracted=2,
    )


@pytest.mark.asyncio
async def test_reject_mode_emits_verified_narrative_sentences():
    results = _synthetic_corpus()
    # Force the pure rules path: no LLM provider, deterministic.
    with patch.object(llm_client, "get_provider", return_value=None):
        agent = LiteratureBuilderAgent(grounding_mode="reject")
        doc = await agent.process(results)

    sentences = [s for sec in doc.sections for s in (sec.sentences or [])]
    assert sentences, "reject-mode narrative produced zero NarrativeSentence objects"
    assert all(s.verified for s in sentences), (
        "under reject grounding every emitted sentence must be verified; got "
        f"{[(s.text, s.verified) for s in sentences]}"
    )
    # Every verified sentence must carry a resolvable \cite{} key.
    assert all(s.cite_keys for s in sentences)
