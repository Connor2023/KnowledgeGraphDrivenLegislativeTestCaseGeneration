"""The comparison arms. Everything here exists to be measured against `spires`.

The pipeline being proposed has one context mode: it walks the SPIRES norm graph. The
other arms are what that claim is argued against, and they are kept -- working, runnable,
unchanged in behaviour -- because a result with no controls is not a result.

    none          section text alone
    full-corpus   the whole flattened corpus pasted in verbatim, target included
    kg            the EDC triple graph: seed, expand, rank, prune, serialise
    kg-text-only  the same retrieval, triples withheld, provision text kept
    rp1           the RP1 concept graph, serialised whole

plus six format probes, which vary only the block 3 header. Those are not proposed
configurations; they measure whether the gaps between arms survive plausible rephrasing
of the framing around them (Sclar et al., ICLR 2024).

HOW THEY PLUG BACK IN. Each arm builds its own context block and hands it to
`kg_testgen.pipeline.run` as an `ExternalContext`. The pipeline never learns these modes
exist -- it has no registry, no plugin lookup and no import of this package -- so the one
direction that would undo the separation cannot happen by accident.

WHY THIS IS NOT IN THE PIPELINE. The EDC arm alone pulls in seeding, retrieval, ranking,
serialisation, the EDC bridge and the whole vendored edc-main tree, and through it
transformers and numpy. Installing a pipeline that generates test cases should not
install a sentence-transformer stack that only the control arm uses.
"""

__all__ = ["build_context", "block3_header", "ARM_MODES"]

from .contexts import ARM_MODES, block3_header, build_context  # noqa: E402,F401
