# Compare Insights implementation findings

The current Compare flow returns extracted paper fields and evidence, but Insights is a frontend synthesis rather than a persisted, versioned run. The PDF parser returns extracted text and caption-level table/figure data; its normal text path removes the references section. It does not currently provide structured study design, datasets metadata, reproducibility fields, author affiliations, full parsed references, or complete table contents. No comparison-specific credits service or saved research-ideas module was found.

New insight content must be limited to fields and passages actually available from uploaded PDFs. Missing facts should be identified as unavailable rather than inferred as source facts. DOI/Crossref, Retraction Watch, and GitHub lookups require external integrations and source labels.
