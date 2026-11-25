pub fn chunk_text(text: &str, chunk_size: usize, overlap: usize, preserve_headings: bool) -> Vec<String> {
    let units = split_structural_units(text, preserve_headings);
    let mut chunks = Vec::new();
    let mut current_words: Vec<&str> = Vec::new();

    for unit in &units {
        let unit_words: Vec<&str> = unit.split_whitespace().collect();
        if unit_words.is_empty() {
            continue;
        }

        if unit_words.len() > chunk_size {
            flush_words(&mut chunks, &current_words);
            current_words.clear();
            chunks.extend(split_words(&unit_words, chunk_size, overlap));
            continue;
        }

        if !current_words.is_empty() && current_words.len() + unit_words.len() > chunk_size {
            flush_words(&mut chunks, &current_words);
            // Shrink the overlap tail so overlap + next unit still fits in chunk_size.
            let keep = overlap
                .min(chunk_size - unit_words.len())
                .min(current_words.len());
            current_words.drain(..current_words.len() - keep);
        }

        current_words.extend(unit_words);
    }

    flush_words(&mut chunks, &current_words);
    chunks
}

fn split_structural_units(text: &str, preserve_headings: bool) -> Vec<String> {
    let mut units = Vec::new();
    let mut current: Vec<&str> = Vec::new();
    let mut in_code_block = false;

    for line in text.lines() {
        let stripped = line.trim();

        if stripped.starts_with("```") {
            current.push(line);
            in_code_block = !in_code_block;
            if !in_code_block {
                push_unit(&mut units, &current);
                current.clear();
            }
            continue;
        }

        if in_code_block {
            current.push(line);
            continue;
        }

        if stripped.is_empty() {
            if !current.is_empty() {
                push_unit(&mut units, &current);
                current.clear();
            }
            continue;
        }

        if preserve_headings && stripped.starts_with('#') {
            if !current.is_empty() {
                push_unit(&mut units, &current);
            }
            current.clear();
            current.push(line);
            continue;
        }

        current.push(line);
    }

    if !current.is_empty() {
        push_unit(&mut units, &current);
    }

    units
}

fn push_unit(units: &mut Vec<String>, lines: &[&str]) {
    let unit = lines.join("\n").trim().to_string();
    if !unit.is_empty() {
        units.push(unit);
    }
}

fn split_words(words: &[&str], chunk_size: usize, overlap: usize) -> Vec<String> {
    let overlap = overlap.min(chunk_size.saturating_sub(1));
    let mut chunks = Vec::new();
    let mut start = 0;

    while start < words.len() {
        let end = (start + chunk_size).min(words.len());
        chunks.push(words[start..end].join(" "));
        if end == words.len() {
            break;
        }
        start = end - overlap;
    }

    chunks
}

fn flush_words(chunks: &mut Vec<String>, words: &[&str]) {
    if !words.is_empty() {
        chunks.push(words.join(" "));
    }
}

#[cfg(test)]
mod tests {
    use super::chunk_text;

    #[test]
    fn overlap_is_trimmed_to_respect_chunk_size_across_units() {
        let chunks = chunk_text("one two three four\n\nfive six seven eight", 5, 4, true);

        assert_eq!(chunks, vec!["one two three four", "four five six seven eight"]);
        assert!(chunks.iter().all(|c| c.split_whitespace().count() <= 5));
    }

    #[test]
    fn overlap_is_dropped_when_next_unit_fills_chunk() {
        let chunks = chunk_text("alpha beta\n\ngamma delta epsilon", 3, 2, true);

        assert_eq!(chunks, vec!["alpha beta", "gamma delta epsilon"]);
    }
}
