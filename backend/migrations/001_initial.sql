CREATE TABLE IF NOT EXISTS analysis_reports (
    id UUID PRIMARY KEY,
    idea_text TEXT NOT NULL,
    idea_title TEXT,
    overall_score_100 INTEGER,
    verdict TEXT,
    confidence TEXT,
    markdown TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES analysis_reports(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    output_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_outputs_analysis_id ON agent_outputs(analysis_id);
CREATE INDEX IF NOT EXISTS idx_analysis_reports_created_at ON analysis_reports(created_at DESC);
