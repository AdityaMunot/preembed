use pyo3::exceptions::PyValueError;
use pyo3::PyErr;
use std::fmt;

#[derive(Debug)]
pub enum PreembedError {
    InvalidConfig { field: String, message: String },
    EmptyInput { operation: String },
    ProcessingError { operation: String, detail: String },
}

impl fmt::Display for PreembedError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidConfig { field, message } => {
                write!(f, "invalid config for '{field}': {message}")
            }
            Self::EmptyInput { operation } => {
                write!(f, "{operation}: received empty input")
            }
            Self::ProcessingError { operation, detail } => {
                write!(f, "{operation} failed: {detail}")
            }
        }
    }
}

impl std::error::Error for PreembedError {}

impl From<PreembedError> for PyErr {
    fn from(err: PreembedError) -> PyErr {
        PyValueError::new_err(err.to_string())
    }
}
