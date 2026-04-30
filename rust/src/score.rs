use std::collections::HashMap;

use crate::dedupe::normalize_for_dedupe;

const LENGTH_WEIGHT: f64 = 0.30;
const DENSITY_WEIGHT: f64 = 0.30;
const DUPLICATE_WEIGHT: f64 = 0.20;
const STRUCTURE_WEIGHT: f64 = 0.20;
const DUPLICATE_PENALTY_SCORE: f64 = 0.35;
const BOILERPLATE_TERM_THRESHOLD: usize = 4;

#[derive(Debug, Clone)]
pub struct ScoredChunk {
    pub text: String,
    pub tokens: usize,
    pub score: f64,
    pub warnings: Vec<String>,
}

pub fn score_chunks(chunks: &[String]) -> Vec<ScoredChunk> {
    let mut normalized_counts: HashMap<String, usize> = HashMap::new();
    let mut normalized_cache: Vec<String> = Vec::with_capacity(chunks.len());
    for chunk in chunks {
        let normalized = normalize_for_dedupe(chunk);
        *normalized_counts.entry(normalized.clone()).or_insert(0) += 1;
        normalized_cache.push(normalized);
    }

    chunks
        .iter()
        .zip(normalized_cache.iter())
        .map(|(chunk, normalized)| score_chunk(chunk, normalized, &normalized_counts))
        .collect()
}

fn score_chunk(chunk: &str, normalized: &str, normalized_counts: &HashMap<String, usize>) -> ScoredChunk {
    let words: Vec<&str> = chunk.split_whitespace().collect();
    let token_count = words.len();
    let mut warnings = Vec::new();

    let length_score = length_score(token_count);
    let density_score = information_density_score(&words);
    let structure_score = structure_score(chunk);

    let duplicate_score = if normalized_counts.get(normalized).copied().unwrap_or(0) > 1 {
        DUPLICATE_PENALTY_SCORE
    } else {
        1.0
    };
    let is_boilerplate = looks_like_boilerplate(chunk);

    if token_count < 20 {
        warnings.push("too_short".to_string());
    }
    if token_count > 900 {
        warnings.push("too_long".to_string());
    }
    if density_score < 0.45 {
        warnings.push("low_information_density".to_string());
    }
    if duplicate_score < 1.0 {
        warnings.push("duplicate_likelihood".to_string());
    }
    if is_boilerplate {
        warnings.push("boilerplate".to_string());
    }

    let raw_score =
        length_score * LENGTH_WEIGHT + density_score * DENSITY_WEIGHT + duplicate_score * DUPLICATE_WEIGHT + structure_score * STRUCTURE_WEIGHT;
    let score = ((raw_score - warning_penalty(&warnings)).clamp(0.0, 1.0) * 1000.0).round() / 1000.0;

    ScoredChunk {
        text: chunk.to_string(),
        tokens: token_count,
        score,
        warnings,
    }
}

fn length_score(token_count: usize) -> f64 {
    if token_count == 0 {
        return 0.0;
    }
    if (80..=700).contains(&token_count) {
        return 1.0;
    }
    if token_count < 80 {
        return (token_count as f64 / 80.0).max(0.2);
    }

    (1.0 - ((token_count - 700) as f64 / 700.0)).max(0.2)
}

fn information_density_score(words: &[&str]) -> f64 {
    if words.is_empty() {
        return 0.0;
    }

    let mut unique = std::collections::HashSet::new();
    for word in words {
        unique.insert(word.to_lowercase());
    }

    let unique_ratio = unique.len() as f64 / words.len() as f64;
    let average_word_length = words.iter().map(|word| word.chars().count()).sum::<usize>() as f64 / words.len() as f64;
    let length_factor = (average_word_length / 5.0).min(1.0);

    ((unique_ratio * 0.7) + (length_factor * 0.3)).clamp(0.0, 1.0)
}

fn structure_score(chunk: &str) -> f64 {
    if chunk.contains("```") {
        return 1.0;
    }
    if has_markdown_heading(chunk) {
        return 1.0;
    }
    if has_list_marker(chunk) {
        return 0.85;
    }
    0.75
}

fn has_markdown_heading(chunk: &str) -> bool {
    let mut prev_was_hashes = false;
    for (i, word) in chunk.split_whitespace().enumerate() {
        if i > 0 && prev_was_hashes {
            return true;
        }
        prev_was_hashes = word.starts_with('#') && word.chars().all(|c| c == '#');
    }
    false
}

fn has_list_marker(chunk: &str) -> bool {
    chunk.split_whitespace().any(|word| {
        word == "-" || word == "*"
            || (word.ends_with('.') && word.len() > 1 && word[..word.len() - 1].chars().all(|c| c.is_ascii_digit()))
    })
}

fn looks_like_boilerplate(chunk: &str) -> bool {
    let normalized = chunk.to_lowercase();
    let terms = [
        "home",
        "login",
        "sign in",
        "privacy policy",
        "terms of service",
        "contact",
        "copyright",
    ];
    let matches = terms.iter().filter(|term| normalized.contains(**term)).count();

    matches >= BOILERPLATE_TERM_THRESHOLD
}

fn warning_penalty(warnings: &[String]) -> f64 {
    warnings
        .iter()
        .map(|warning| match warning.as_str() {
            "boilerplate" => 0.25,
            "duplicate_likelihood" => 0.15,
            "low_information_density" => 0.15,
            "too_short" | "too_long" => 0.05,
            _ => 0.0,
        })
        .sum()
}

#[cfg(test)]
mod tests {
    use super::score_chunks;

    #[test]
    fn scores_well_structured_chunk_above_warning_heavy_examples() {
        let scored = score_chunks(&[String::from(
            "# Account Recovery\nAdministrators can rotate recovery tokens after confirming requester identity, reviewing audit logs, recording the approval ticket, and notifying the security team.",
        )]);

        assert!(scored[0].score >= 0.70);
        assert!(scored[0].warnings.is_empty());
    }

    #[test]
    fn penalizes_low_information_repetition() {
        let scored = score_chunks(&[String::from(
            "status status status status status status status status status status status status status status status status status status status status",
        )]);

        assert!(scored[0].score < 0.40);
        assert!(scored[0].warnings.contains(&"low_information_density".to_string()));
    }

    #[test]
    fn penalizes_boilerplate_heavily() {
        let scored = score_chunks(&[String::from(
            "Home Login Contact Privacy Policy Terms of Service Copyright Home Login Contact Privacy Policy Terms of Service Copyright",
        )]);

        assert!(scored[0].score < 0.40);
        assert!(scored[0].warnings.contains(&"boilerplate".to_string()));
    }

    #[test]
    fn penalizes_duplicated_chunks() {
        let chunks = vec![
            String::from("This chunk explains account recovery tokens, audit log retention, administrator approval workflows, requester verification steps, and escalation handling."),
            String::from("This chunk explains account recovery tokens, audit log retention, administrator approval workflows, requester verification steps, and escalation handling."),
        ];
        let scored = score_chunks(&chunks);

        assert!(scored[0].score < 0.60);
        assert!(scored[0].warnings.contains(&"duplicate_likelihood".to_string()));
    }

    #[test]
    fn code_heavy_chunks_keep_structure_credit() {
        let scored = score_chunks(&[String::from(
            "```python\ndef normalize(items):\n    cleaned = []\n    for item in items:\n        if item:\n            cleaned.append(item.strip().lower())\n    return cleaned\n```\nThe helper normalizes identifiers before duplicate comparison.",
        )]);

        assert!(scored[0].score >= 0.60);
    }
}
