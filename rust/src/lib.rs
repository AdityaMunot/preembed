pub mod clean;
pub mod chunk;
pub mod dedupe;
pub mod score;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

#[pyfunction]
fn normalize_whitespace(text: &str) -> String {
    clean::normalize_whitespace(text)
}

#[pyfunction]
fn clean_text(text: &str) -> String {
    clean::clean_text(text)
}

#[pyfunction]
fn chunk_text(text: &str, chunk_size: usize, overlap: usize, preserve_headings: bool) -> Vec<String> {
    chunk::chunk_text(text, chunk_size, overlap, preserve_headings)
}

#[pyfunction]
fn dedupe_chunks(
    py: Python<'_>,
    chunks: Vec<String>,
    near_duplicate_threshold: f64,
    exact: bool,
    normalized: bool,
    near_duplicates: bool,
) -> PyResult<PyObject> {
    let result = dedupe::dedupe_chunks_with_config(
        &chunks,
        dedupe::DedupeConfig {
            near_duplicate_threshold,
            exact,
            normalized,
            near_duplicates,
        },
    );
    let output = PyDict::new_bound(py);

    output.set_item("retained_chunks", result.retained_chunks)?;
    output.set_item("removed_chunks", result.removed_chunks)?;
    output.set_item("duplicate_count", result.duplicate_count)?;
    output.set_item("duplicate_ratio", result.duplicate_ratio)?;
    output.set_item(
        "duplicate_groups",
        duplicate_groups_to_py(py, result.duplicate_groups)?,
    )?;
    output.set_item(
        "duplicate_metadata",
        duplicate_metadata_to_py(py, result.duplicate_metadata)?,
    )?;

    Ok(output.into())
}

fn duplicate_groups_to_py(py: Python<'_>, groups: Vec<dedupe::DuplicateGroup>) -> PyResult<PyObject> {
    let output = PyList::empty_bound(py);

    for group in groups {
        let item = PyDict::new_bound(py);
        item.set_item("retained_index", group.retained_index)?;
        item.set_item("retained_chunk", group.retained_chunk)?;
        item.set_item("duplicates", duplicate_metadata_to_py(py, group.duplicates)?)?;
        output.append(item)?;
    }

    Ok(output.into())
}

fn duplicate_metadata_to_py(
    py: Python<'_>,
    metadata: Vec<dedupe::DuplicateMetadata>,
) -> PyResult<PyObject> {
    let output = PyList::empty_bound(py);

    for duplicate in metadata {
        let item = PyDict::new_bound(py);
        item.set_item("index", duplicate.index)?;
        item.set_item("chunk", duplicate.chunk)?;
        item.set_item("retained_index", duplicate.retained_index)?;
        item.set_item("retained_chunk", duplicate.retained_chunk)?;
        item.set_item("kind", duplicate.kind)?;
        item.set_item("similarity", duplicate.similarity)?;
        output.append(item)?;
    }

    Ok(output.into())
}

#[pyfunction]
fn score_chunks(py: Python<'_>, chunks: Vec<String>) -> PyResult<PyObject> {
    let output = PyList::empty_bound(py);

    for scored in score::score_chunks(&chunks) {
        let item = PyDict::new_bound(py);
        item.set_item("text", scored.text)?;
        item.set_item("tokens", scored.tokens)?;
        item.set_item("score", scored.score)?;
        item.set_item("warnings", scored.warnings)?;
        output.append(item)?;
    }

    Ok(output.into())
}

#[pymodule]
fn preembed_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(normalize_whitespace, module)?)?;
    module.add_function(wrap_pyfunction!(clean_text, module)?)?;
    module.add_function(wrap_pyfunction!(chunk_text, module)?)?;
    module.add_function(wrap_pyfunction!(dedupe_chunks, module)?)?;
    module.add_function(wrap_pyfunction!(score_chunks, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{chunk_text, clean_text, normalize_whitespace};
    use crate::{dedupe, score};

    #[test]
    fn normalizes_whitespace() {
        assert_eq!(normalize_whitespace("a\n\n  b\tc"), "a b c");
    }

    #[test]
    fn strips_basic_html() {
        assert_eq!(clean_text("<h1>Hello</h1><p>world</p>"), "Hello world");
    }

    #[test]
    fn strips_script_and_style_blocks_with_attributes() {
        assert_eq!(
            clean_text("<STYLE type=\"text/css\">.x{}</STYLE><p>Hello</p><script>x()</script>"),
            "Hello"
        );
    }

    #[test]
    fn chunks_with_overlap() {
        assert_eq!(
            chunk_text("one two three four five", 3, 1, true),
            vec!["one two three".to_string(), "three four five".to_string()]
        );
    }

    #[test]
    fn dedupes_normalized_chunks() {
        let chunks = vec!["Hello   world".to_string(), "hello world".to_string()];
        let result = dedupe::dedupe_chunks(&chunks, 0.9);

        assert_eq!(result.retained_chunks, vec!["Hello   world".to_string()]);
        assert_eq!(result.duplicate_count, 1);
        assert_eq!(result.duplicate_metadata[0].kind, "normalized");
    }

    #[test]
    fn dedupe_config_can_disable_normalized_chunks() {
        let chunks = vec!["Hello   world".to_string(), "hello world".to_string()];
        let result = dedupe::dedupe_chunks_with_config(
            &chunks,
            dedupe::DedupeConfig {
                exact: true,
                normalized: false,
                near_duplicates: false,
                ..dedupe::DedupeConfig::default()
            },
        );

        assert_eq!(result.retained_chunks, chunks);
        assert_eq!(result.duplicate_count, 0);
    }

    #[test]
    fn dedupe_config_controls_near_duplicate_threshold() {
        let chunks = vec![
            "alpha beta gamma delta epsilon zeta eta".to_string(),
            "alpha beta gamma delta epsilon zeta theta".to_string(),
        ];
        let permissive = dedupe::dedupe_chunks_with_config(
            &chunks,
            dedupe::DedupeConfig {
                near_duplicate_threshold: 0.6,
                exact: false,
                normalized: false,
                near_duplicates: true,
            },
        );
        let strict = dedupe::dedupe_chunks_with_config(
            &chunks,
            dedupe::DedupeConfig {
                near_duplicate_threshold: 0.9,
                exact: false,
                normalized: false,
                near_duplicates: true,
            },
        );

        assert_eq!(permissive.retained_chunks, vec![chunks[0].clone()]);
        assert_eq!(permissive.duplicate_metadata[0].kind, "near_duplicate");
        assert_eq!(strict.retained_chunks, chunks);
    }

    #[test]
    fn scores_boilerplate() {
        let chunks = vec![
            "Home Login About Contact Privacy Policy".to_string(),
            "Home Login About Contact Privacy Policy".to_string(),
        ];
        let scored = score::score_chunks(&chunks);

        assert!(scored[0].warnings.contains(&"boilerplate".to_string()));
        assert!(scored[0].warnings.contains(&"duplicate_likelihood".to_string()));
    }
}

#[cfg(test)]
mod proptest_fuzz {
    use proptest::prelude::*;
    use crate::{chunk, clean, dedupe, score};

    proptest! {
        #[test]
        fn clean_text_never_panics(s in "\\PC{0,5000}") {
            let _ = clean::clean_text(&s);
        }

        #[test]
        fn clean_text_strips_script(body in "\\PC{0,500}") {
            let input = format!("<script>{body}</script><p>keep</p>");
            let result = clean::clean_text(&input);
            assert!(!result.to_lowercase().contains("<script>"));
        }

        #[test]
        fn chunk_text_respects_size(
            s in "([a-z]{1,10} ){5,200}",
            chunk_size in 2usize..200,
            overlap in 0usize..50,
        ) {
            prop_assume!(overlap < chunk_size);
            let chunks = chunk::chunk_text(&s, chunk_size, overlap, true);
            for c in &chunks {
                let words: Vec<&str> = c.split_whitespace().collect();
                prop_assert!(words.len() <= chunk_size, "chunk has {} words, max {}", words.len(), chunk_size);
            }
        }

        #[test]
        fn chunk_text_never_panics(
            s in "\\PC{0,3000}",
            chunk_size in 1usize..500,
            overlap in 0usize..499,
        ) {
            prop_assume!(overlap < chunk_size);
            let _ = chunk::chunk_text(&s, chunk_size, overlap, true);
        }

        #[test]
        fn dedupe_never_adds(chunks in proptest::collection::vec("\\PC{1,200}", 0..30)) {
            let result = dedupe::dedupe_chunks_with_config(&chunks, dedupe::DedupeConfig::default());
            prop_assert!(result.retained_chunks.len() <= chunks.len());
        }

        #[test]
        fn dedupe_retained_subset(chunks in proptest::collection::vec("\\PC{1,200}", 1..30)) {
            let result = dedupe::dedupe_chunks_with_config(&chunks, dedupe::DedupeConfig::default());
            for r in &result.retained_chunks {
                prop_assert!(chunks.contains(r));
            }
        }

        #[test]
        fn score_in_range(chunks in proptest::collection::vec("\\PC{1,300}", 1..20)) {
            let scored = score::score_chunks(&chunks);
            prop_assert_eq!(scored.len(), chunks.len());
            for s in &scored {
                prop_assert!(s.score >= 0.0 && s.score <= 1.0, "score {} out of range", s.score);
            }
        }

        #[test]
        fn normalize_never_panics(s in "\\PC{0,1000}") {
            let _ = dedupe::normalize_for_dedupe(&s);
        }
    }
}
