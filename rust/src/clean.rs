pub fn normalize_whitespace(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut needs_space = false;

    for part in text.split_whitespace() {
        if needs_space {
            output.push(' ');
        }
        output.push_str(part);
        needs_space = true;
    }

    output
}

pub fn clean_text(text: &str) -> String {
    let without_tags = strip_html_noise(text, false);

    normalize_whitespace(&without_tags)
}

/// Clean text while keeping line and paragraph boundaries so structural chunking still works.
pub fn clean_text_structured(text: &str) -> String {
    let without_tags = strip_html_noise(text, true);

    normalize_structure(&without_tags)
}

/// Collapse whitespace within lines and keep at most one blank line between blocks.
pub fn normalize_structure(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut pending_blank = false;

    for line in text.lines() {
        let normalized = normalize_whitespace(line);
        if normalized.is_empty() {
            pending_blank = !output.is_empty();
            continue;
        }
        if !output.is_empty() {
            output.push_str(if pending_blank { "\n\n" } else { "\n" });
        }
        output.push_str(&normalized);
        pending_blank = false;
    }

    output
}

fn strip_html_noise(text: &str, keep_blocks: bool) -> String {
    let mut output = String::with_capacity(text.len());
    let mut index = 0;

    while index < text.len() {
        let remaining = &text[index..];

        if remaining.starts_with('<') {
            let Some(tag_end_offset) = remaining.find('>') else {
                output.push_str(remaining);
                break;
            };

            let tag_end = index + tag_end_offset;
            let tag = &text[index + 1..tag_end];

            if let Some(name) = noise_block_name(tag) {
                let close = find_block_end(text, tag_end + 1, name);
                // Unclosed script/style hides everything after it; unclosed layout tags hide nothing.
                let end = close.or_else(|| SCRIPT_TAGS.contains(&name).then_some(text.len()));
                if let Some(end) = end {
                    index = end;
                    output.push_str(tag_separator(name, keep_blocks));
                    continue;
                }
            }

            let separator = tag_separator(tag, keep_blocks);
            // Adjacent line-level tags (e.g. `</li><li>`) must not stack into a paragraph break.
            if !(separator == "\n" && output.ends_with('\n')) {
                output.push_str(separator);
            }
            index = tag_end + 1;
            continue;
        }

        let character = remaining.chars().next().expect("remaining text is not empty");
        output.push(character);
        index += character.len_utf8();
    }

    output
}

fn tag_separator(tag: &str, keep_blocks: bool) -> &'static str {
    if !keep_blocks {
        return " ";
    }

    let name = tag
        .trim_start()
        .trim_start_matches('/')
        .split(|character: char| character.is_whitespace() || character == '/' || character == '>')
        .next()
        .unwrap_or("");

    const LINE_TAGS: [&str; 4] = ["br", "li", "tr", "dt"];
    const BLOCK_TAGS: [&str; 22] = [
        "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "section", "article",
        "header", "footer", "nav", "aside", "main", "pre", "blockquote", "hr", "dl",
    ];

    if LINE_TAGS.iter().any(|t| name.eq_ignore_ascii_case(t)) {
        "\n"
    } else if BLOCK_TAGS.iter().any(|t| name.eq_ignore_ascii_case(t)) {
        "\n\n"
    } else {
        " "
    }
}

const SCRIPT_TAGS: [&str; 2] = ["script", "style"];
const NOISE_TAGS: [&str; 7] = ["script", "style", "noscript", "template", "svg", "nav", "footer"];

fn noise_block_name(tag: &str) -> Option<&'static str> {
    if tag.trim_end().ends_with('/') {
        return None;
    }
    NOISE_TAGS.into_iter().find(|name| is_opening_tag(tag, name))
}

fn find_block_end(text: &str, start: usize, tag: &str) -> Option<usize> {
    let close_prefix = format!("</{}", tag);
    let close_start = find_ascii_case_insensitive(text, start, &close_prefix)?;
    let close_end_offset = text[close_start..].find('>')?;

    Some(close_start + close_end_offset + 1)
}

fn is_opening_tag(tag: &str, expected: &str) -> bool {
    let trimmed = tag.trim_start();

    if trimmed.starts_with('/') || trimmed.starts_with('!') || trimmed.starts_with('?') {
        return false;
    }

    let name = trimmed
        .split(|character: char| character.is_whitespace() || character == '/' || character == '>')
        .next()
        .unwrap_or("");

    name.eq_ignore_ascii_case(expected)
}

fn find_ascii_case_insensitive(haystack: &str, start: usize, needle: &str) -> Option<usize> {
    let haystack_bytes = haystack.as_bytes();
    let needle_bytes = needle.as_bytes();

    if needle_bytes.is_empty() || start >= haystack_bytes.len() {
        return None;
    }

    haystack_bytes[start..]
        .windows(needle_bytes.len())
        .position(|window| {
            window
                .iter()
                .zip(needle_bytes.iter())
                .all(|(left, right)| left.eq_ignore_ascii_case(right))
        })
        .map(|relative_position| start + relative_position)
}

#[cfg(test)]
mod tests {
    use super::{clean_text, clean_text_structured};

    #[test]
    fn structured_clean_keeps_paragraph_breaks_for_markdown() {
        let source = "# Title\n\n\n\nFirst   para\nline two\n\n```\ncode  here\n```";

        assert_eq!(
            clean_text_structured(source),
            "# Title\n\nFirst para\nline two\n\n```\ncode here\n```"
        );
    }

    #[test]
    fn structured_clean_turns_html_blocks_into_paragraphs() {
        let source = "<h1>Title</h1><p>Alpha <b>bold</b></p><script>x()</script><ul><li>one</li><li>two</li></ul>";

        assert_eq!(clean_text_structured(source), "Title\n\nAlpha bold\n\none\ntwo");
    }

    #[test]
    fn drops_navigation_footer_and_inline_svg() {
        let source = "<nav><a>Home</a> <a>Login</a></nav><p>Body</p><svg><path d='M0'/></svg><footer>Copyright</footer>";

        assert_eq!(clean_text(source), "Body");
    }

    #[test]
    fn unclosed_layout_tag_keeps_following_content() {
        assert_eq!(clean_text("<nav>Menu<p>Body text</p>"), "Menu Body text");
    }

    #[test]
    fn self_closing_noise_tag_keeps_following_content() {
        assert_eq!(clean_text("<svg width='1'/><p>Body</p>"), "Body");
    }

    #[test]
    fn unclosed_script_still_hides_trailing_code() {
        assert_eq!(clean_text("<p>Body</p><script>track()"), "Body");
    }

    #[test]
    fn flat_clean_is_unchanged() {
        assert_eq!(clean_text("<h1>Title</h1><p>Alpha</p>\n\nBeta"), "Title Alpha Beta");
    }
}
