use std::collections::hash_map::DefaultHasher;
use std::collections::HashMap;
use std::collections::HashSet;
use std::hash::{Hash, Hasher};

#[derive(Debug, Clone)]
pub struct DedupeOutput {
    pub retained_chunks: Vec<String>,
    pub removed_chunks: Vec<String>,
    pub duplicate_count: usize,
    pub duplicate_ratio: f64,
    pub duplicate_groups: Vec<DuplicateGroup>,
    pub duplicate_metadata: Vec<DuplicateMetadata>,
}

#[derive(Debug, Clone)]
pub struct DuplicateGroup {
    pub retained_index: usize,
    pub retained_chunk: String,
    pub duplicates: Vec<DuplicateMetadata>,
}

#[derive(Debug, Clone)]
pub struct DuplicateMetadata {
    pub index: usize,
    pub chunk: String,
    pub retained_index: usize,
    pub retained_chunk: String,
    pub kind: String,
    pub similarity: f64,
}

#[derive(Debug, Clone)]
pub struct DedupeConfig {
    pub near_duplicate_threshold: f64,
    pub exact: bool,
    pub normalized: bool,
    pub near_duplicates: bool,
}

impl Default for DedupeConfig {
    fn default() -> Self {
        Self {
            near_duplicate_threshold: 0.9,
            exact: true,
            normalized: true,
            near_duplicates: true,
        }
    }
}

#[derive(Debug, Clone)]
struct RetainedRecord {
    index: usize,
    chunk: String,
    fingerprint: HashSet<u64>,
}

#[derive(Debug, Clone)]
struct DuplicateMatch {
    retained_index: usize,
    retained_chunk: String,
    kind: String,
    similarity: f64,
}

#[allow(dead_code)]
pub fn dedupe_chunks(chunks: &[String], near_duplicate_threshold: f64) -> DedupeOutput {
    dedupe_chunks_with_config(
        chunks,
        DedupeConfig {
            near_duplicate_threshold,
            ..DedupeConfig::default()
        },
    )
}

pub fn dedupe_chunks_with_config(chunks: &[String], config: DedupeConfig) -> DedupeOutput {
    let mut retained_chunks = Vec::new();
    let mut removed_chunks = Vec::new();
    let mut retained_records: Vec<RetainedRecord> = Vec::new();
    let mut duplicate_metadata: Vec<DuplicateMetadata> = Vec::new();
    let mut duplicate_groups: Vec<DuplicateGroup> = Vec::new();
    let mut group_index: HashMap<usize, usize> = HashMap::new(); // retained_index → groups vec index

    // O(1) lookup indices for exact and normalized matching.
    let mut exact_index: HashMap<String, usize> = HashMap::new();
    let mut normalized_index: HashMap<String, usize> = HashMap::new();
    // Inverted index: fingerprint hash → list of retained record indices that contain it.
    let mut fingerprint_index: HashMap<u64, Vec<usize>> = HashMap::new();

    for (index, chunk) in chunks.iter().enumerate() {
        let normalized = normalize_for_dedupe(chunk);
        let fingerprint = fingerprint(&normalized);

        if let Some(duplicate) = find_duplicate_indexed(
            chunk,
            &normalized,
            &fingerprint,
            &retained_records,
            &exact_index,
            &normalized_index,
            &fingerprint_index,
            &config,
        ) {
            removed_chunks.push(chunk.clone());
            let metadata = DuplicateMetadata {
                index,
                chunk: chunk.clone(),
                retained_index: duplicate.retained_index,
                retained_chunk: duplicate.retained_chunk.clone(),
                kind: duplicate.kind,
                similarity: duplicate.similarity,
            };
            add_duplicate_to_group(&mut duplicate_groups, &mut group_index, &metadata);
            duplicate_metadata.push(metadata);
            continue;
        }

        let record_index = retained_records.len();

        // Insert into lookup indices.
        if config.exact {
            exact_index.entry(chunk.clone()).or_insert(record_index);
        }
        if config.normalized && !normalized.is_empty() {
            normalized_index.entry(normalized.clone()).or_insert(record_index);
        }
        if config.near_duplicates {
            for &hash in &fingerprint {
                fingerprint_index.entry(hash).or_default().push(record_index);
            }
        }

        retained_records.push(RetainedRecord {
            index,
            chunk: chunk.clone(),
            fingerprint,
        });
        retained_chunks.push(chunk.clone());
    }

    let total = retained_chunks.len() + removed_chunks.len();
    let duplicate_count = removed_chunks.len();
    let duplicate_ratio = if total == 0 {
        0.0
    } else {
        duplicate_count as f64 / total as f64
    };

    DedupeOutput {
        retained_chunks,
        removed_chunks,
        duplicate_count,
        duplicate_ratio,
        duplicate_groups,
        duplicate_metadata,
    }
}

pub fn normalize_for_dedupe(chunk: &str) -> String {
    let mut output = String::with_capacity(chunk.len());
    let mut previous_was_space = true;

    for character in chunk.chars().flat_map(char::to_lowercase) {
        if character.is_alphanumeric() || character == '_' {
            output.push(character);
            previous_was_space = false;
        } else if !previous_was_space {
            output.push(' ');
            previous_was_space = true;
        }
    }

    output.trim().to_string()
}

fn fingerprint(normalized: &str) -> HashSet<u64> {
    let words: Vec<&str> = normalized.split_whitespace().collect();
    let mut hashes = HashSet::new();

    if words.len() < 3 {
        if !normalized.is_empty() {
            hashes.insert(stable_hash(normalized));
        }
        return hashes;
    }

    for window in words.windows(3) {
        hashes.insert(stable_hash(&window.join(" ")));
    }

    hashes
}

fn stable_hash(value: &str) -> u64 {
    let mut hasher = DefaultHasher::new();
    value.hash(&mut hasher);
    hasher.finish()
}

fn find_duplicate_indexed(
    chunk: &str,
    normalized: &str,
    fingerprint: &HashSet<u64>,
    retained_records: &[RetainedRecord],
    exact_index: &HashMap<String, usize>,
    normalized_index: &HashMap<String, usize>,
    fingerprint_index: &HashMap<u64, Vec<usize>>,
    config: &DedupeConfig,
) -> Option<DuplicateMatch> {
    // O(1) exact lookup.
    if config.exact {
        if let Some(&record_idx) = exact_index.get(chunk) {
            return Some(duplicate_match(&retained_records[record_idx], "exact", 1.0));
        }
    }

    // O(1) normalized lookup.
    if config.normalized && !normalized.is_empty() {
        if let Some(&record_idx) = normalized_index.get(normalized) {
            return Some(duplicate_match(&retained_records[record_idx], "normalized", 1.0));
        }
    }

    if !config.near_duplicates || fingerprint.is_empty() {
        return None;
    }

    // Inverted index: collect candidate records that share at least one fingerprint hash.
    let mut candidate_hits: HashMap<usize, usize> = HashMap::new();
    for hash in fingerprint {
        if let Some(record_indices) = fingerprint_index.get(hash) {
            for &record_idx in record_indices {
                *candidate_hits.entry(record_idx).or_insert(0) += 1;
            }
        }
    }

    // Only compute full Jaccard similarity for candidates with enough shared hashes.
    let mut best_match: Option<&RetainedRecord> = None;
    let mut best_similarity = 0.0;

    for (&record_idx, &shared_count) in &candidate_hits {
        let record = &retained_records[record_idx];
        // Upper bound prune: if shared hashes can't possibly meet the threshold, skip.
        let max_possible_intersection = shared_count;
        let min_possible_union = fingerprint.len().max(record.fingerprint.len());
        if min_possible_union > 0
            && (max_possible_intersection as f64 / min_possible_union as f64) < config.near_duplicate_threshold
        {
            continue;
        }

        let similarity = fingerprint_similarity(fingerprint, &record.fingerprint);
        if similarity > best_similarity {
            best_similarity = similarity;
            best_match = Some(record);
        }
    }

    if best_similarity >= config.near_duplicate_threshold {
        return best_match
            .map(|record| duplicate_match(record, "near_duplicate", round_similarity(best_similarity)));
    }

    None
}

fn duplicate_match(record: &RetainedRecord, kind: &str, similarity: f64) -> DuplicateMatch {
    DuplicateMatch {
        retained_index: record.index,
        retained_chunk: record.chunk.clone(),
        kind: kind.to_string(),
        similarity,
    }
}

fn add_duplicate_to_group(groups: &mut Vec<DuplicateGroup>, group_index: &mut HashMap<usize, usize>, metadata: &DuplicateMetadata) {
    if let Some(&idx) = group_index.get(&metadata.retained_index) {
        groups[idx].duplicates.push(metadata.clone());
    } else {
        let idx = groups.len();
        group_index.insert(metadata.retained_index, idx);
        groups.push(DuplicateGroup {
            retained_index: metadata.retained_index,
            retained_chunk: metadata.retained_chunk.clone(),
            duplicates: vec![metadata.clone()],
        });
    }
}

fn fingerprint_similarity(fingerprint: &HashSet<u64>, existing: &HashSet<u64>) -> f64 {
    let union = fingerprint.union(existing).count();
    if union == 0 {
        return 0.0;
    }

    let intersection = fingerprint.intersection(existing).count();
    intersection as f64 / union as f64
}

fn round_similarity(value: f64) -> f64 {
    (value * 1000.0).round() / 1000.0
}
