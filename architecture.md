flowchart TB
  subgraph ui [Frontend]
    Composer[ChatComposer_chips_plus_text]
    Page[ChatPage_SSE]
  end

  subgraph api [API_stream_chat]
    Scope[resolve_document_scope]
    Strip[strip_at_mentions]
    Intent[classify_intent]
    Rewrite[maybe_rewrite_query]
  end

  subgraph modes [Intent_routing]
    QA[qa]
    Sum[summarize]
    Cmp[compare]
  end

  subgraph ctx [Context_sources]
    Hybrid[hybrid_retrieve_pooled]
    PerDoc[hybrid_retrieve_per_document]
    SumDB[DocumentSummary_ingest]
    Ready[list_ready_documents]
  end

  subgraph stores [Stores]
    PG[(Postgres_chunks_FTS)]
    QD[(Qdrant_vectors)]
    SumTable[(document_summaries)]
  end

  subgraph out [Answer]
    Prompt[build_chat_messages]
    LLM[Groq_stream]
    Cite[filter_citations]
  end

  Composer --> Page
  Page -->|"message + document_ids"| Scope
  Scope --> Strip
  Strip --> Intent
  Intent --> Rewrite

  Intent --> QA
  Intent --> Sum
  Intent --> Cmp

  QA --> Hybrid
  Sum --> SumDB
  Sum -->|"missing summaries"| PerDoc
  Cmp -->|"no chips"| Ready
  Ready --> PerDoc
  Cmp -->|"with chips"| PerDoc

  Hybrid --> PG
  Hybrid --> QD
  PerDoc --> PG
  PerDoc --> QD
  SumDB --> SumTable

  Hybrid --> Prompt
  PerDoc --> Prompt
  SumDB --> Prompt
  Prompt --> LLM
  LLM --> Cite
