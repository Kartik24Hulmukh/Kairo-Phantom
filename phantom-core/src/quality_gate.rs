use rand::Rng;

pub struct SentinelHashDetector {
    current_hash: String,
}

impl Default for SentinelHashDetector {
    fn default() -> Self {
        Self::new()
    }
}

impl SentinelHashDetector {
    pub fn new() -> Self {
        let hash: String = rand::thread_rng()
            .sample_iter(&rand::distributions::Alphanumeric)
            .take(32)
            .map(char::from)
            .collect();
        Self { current_hash: hash }
    }

    pub fn get_hash(&self) -> &str {
        &self.current_hash
    }

    pub fn scan_output(&self, output: &str) -> Result<(), String> {
        if output.contains(&self.current_hash) {
            return Err("Sentinel hash leak detected in output".to_string());
        }
        if output.to_lowercase().contains("swarm role")
            || output.to_lowercase().contains("swarm brain")
        {
            return Err("System prompt role leak detected in output".to_string());
        }
        Ok(())
    }
}

pub struct IntegrityGateChecklist;
impl IntegrityGateChecklist {
    pub fn check(output: &str, _context: &str) -> Result<(), String> {
        let lower_output = output.to_lowercase();

        // 1. Block obvious placeholder non-responses
        if lower_output.contains("[placeholder]") || lower_output.contains("insert text here") {
            return Err("Integrity check failed: Placeholder text detected.".to_string());
        }

        // 2. Block empty / too-short responses (must have at least 8 real chars)
        if output.len() < 8 && output.chars().filter(|c| c.is_alphanumeric()).count() < 5 {
            return Err("Integrity check failed: Response too short.".to_string());
        }

        // 3. Block AI persona frame-lock (model ignoring the task)
        if lower_output.contains("as an ai, i cannot") || lower_output.contains("i am not able to")
        {
            return Err("Integrity check failed: AI refusal detected.".to_string());
        }

        Ok(())
    }
}

pub struct MultiReviewerPipeline;
impl MultiReviewerPipeline {
    pub fn review(output: &str) -> Result<(), String> {
        let lower_output = output.to_lowercase();

        // Devil's Advocate: Look for contradictions or excessive hedging
        if (output.contains("however") && output.contains("but") && output.len() < 100)
            || lower_output.contains("it is possible that")
        {
            return Err(
                "Devil's Advocate rejected: Possible internal contradiction or excessive hedging."
                    .to_string(),
            );
        }

        // Style Reviewer: Check for "stiff" or "AI-like" phrasing
        let stiff_phrases = [
            "it is important to note",
            "delve into",
            "tapestry of",
            "in conclusion",
            "to summarize",
            "not only but also",
            "furthermore",
            "moreover",
            "in summary",
            "essentially",
            "crucially",
        ];
        for phrase in stiff_phrases {
            if lower_output.contains(phrase) {
                return Err(format!(
                    "Style Reviewer rejected: Detected overused AI phrasing ('{phrase}')."
                ));
            }
        }

        // Check for informalities as requested in kairo-intel.md
        let informal = ["gotta", "cuz", "theyre", "lol", "alright", "wanna", "gonna"];
        for word in informal {
            if lower_output.contains(word) {
                return Err(format!(
                    "Style Reviewer rejected: Informal language or slang detected ('{word}')."
                ));
            }
        }

        // Check for "Assistant" persona
        if lower_output.contains("how can i help") || lower_output.contains("happy to assist") {
            return Err("Style Reviewer rejected: Assistant persona detected.".to_string());
        }

        Ok(())
    }
}

pub fn anti_leakage_format(
    system: &str,
    context: &str,
    user_prompt: &str,
    sentinel: &str,
) -> String {
    format!(
        "<system>\n{system}\nSentinel: {sentinel}\n</system>\n<document_context>\n{context}\n</document_context>\n<user_prompt>\n{user_prompt}\n</user_prompt>\nOutput your response between <output> and </output> tags."
    )
}
