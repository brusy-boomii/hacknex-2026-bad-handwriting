import { useState, useEffect } from 'react'
import './index.css'

function App() {
  const [systemStatus, setSystemStatus] = useState(null)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [editableText, setEditableText] = useState('')
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/health')
      .then(res => res.json())
      .then(data => setSystemStatus(data))
      .catch(err => {
        console.error('Health check failed:', err)
        setSystemStatus({ status: 'error', description: 'Could not connect to backend' })
      })
  }, [])

  useEffect(() => {
    return () => {
      if (preview) {
        URL.revokeObjectURL(preview)
      }
    }
  }, [preview])

  const selectFile = (selectedFile) => {
    if (!selectedFile) return
    setFile(selectedFile)
    if (selectedFile.type && selectedFile.type.startsWith('image/')) {
      setPreview(URL.createObjectURL(selectedFile))
    } else {
      setPreview(null)
    }
    setResult(null)
    setEditableText('')
    setError(null)
  }

  const handleFileChange = (e) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      selectFile(selectedFile)
    }
  }

  const handleDragEnter = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (!isDragging) {
      setIsDragging(true)
    }
  }

  const handleDragLeave = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    const droppedFile = e.dataTransfer?.files?.[0]
    if (droppedFile) {
      selectFile(droppedFile)
    }
  }

  const handleUpload = async () => {
    if (!file) return

    setIsAnalyzing(true)
    setError(null)
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        body: formData,
      })

      let data = {}
      try {
        data = await response.json()
      } catch {
        throw new Error(`Server returned status ${response.status}`)
      }

      if (!response.ok) {
        const detail = typeof data.detail === 'string'
          ? data.detail
          : JSON.stringify(data.detail || 'Analysis failed')
        throw new Error(detail)
      }

      setResult(data)
      setEditableText(data.recognition?.text ?? '')
    } catch (err) {
      setError(err.message)
    } finally {
      setIsAnalyzing(false)
    }
  }

  const formatConfidence = (conf) => {
    if (conf === null || conf === undefined) return 'N/A'
    return `${(conf * 100).toFixed(1)}%`
  }

  return (
    <div className="App">
      <header className="header">
        <h1>Extreme Bad-Handwriting Digitizing Stack</h1>
        <p className="subtitle">HACKNEX 2026 | Project HNX26EPS04</p>

        {systemStatus && (
          <div style={{ marginTop: '1rem' }}>
            <span className={`status-badge ${systemStatus.status === 'healthy' ? 'status-healthy' : 'status-error'}`}>
              System: {systemStatus.status}
            </span>
            <span style={{ marginLeft: '1rem', color: '#888', fontSize: '0.9rem' }}>
              Phase: {systemStatus.phase || 'N/A'} | {systemStatus.description}
            </span>
          </div>
        )}
      </header>

      <main>
        <div className="card">
          <h2>1. Document Ingestion & Upload</h2>
          <p>Upload a handwritten document image to run validation, preprocessing, and optical recognition.</p>

          <div
            className={`upload-section ${isDragging ? 'dragging' : ''}`}
            onClick={() => document.getElementById('fileInput').click()}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {preview ? (
              <div className="preview-container">
                <img src={preview} alt="Uploaded document preview" className="preview-image" />
                {file && (
                  <p className="file-caption">
                    Original File: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
                  </p>
                )}
              </div>
            ) : (
              <div style={{ padding: '2rem' }}>
                <p>{file ? `Selected: ${file.name}` : 'Click to select or drag and drop image'}</p>
                <p style={{ fontSize: '0.8rem', color: '#888' }}>Supported: PNG, JPG, JPEG, TIFF, BMP (Max 10MB)</p>
              </div>
            )}
            <input
              id="fileInput"
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              style={{ display: 'none' }}
            />
          </div>

          <div style={{ marginTop: '1.5rem' }}>
            <button
              onClick={handleUpload}
              disabled={!file || isAnalyzing}
              className="primary-btn"
            >
              {isAnalyzing ? 'Running Recognition Pipeline...' : 'Run Digitization Analysis'}
            </button>
          </div>
        </div>

        {error && (
          <div className="card error-card">
            <h3 style={{ color: '#ef5350', marginTop: 0 }}>Pipeline Error</h3>
            <p style={{ marginBottom: 0 }}>{error}</p>
          </div>
        )}

        {result && (
          <div className="results-stack">
            <div className="card">
              <div className="section-header">
                <h2>2. Recognition Telemetry & Document Metadata</h2>
                <span className="status-badge status-healthy">{result.pipeline_status}</span>
              </div>
              <p className="summary-message">{result.message}</p>

              <div className="metrics-grid">
                <div className="metric-box">
                  <span className="metric-label">Original Filename</span>
                  <span className="metric-value">{result.filename}</span>
                </div>
                <div className="metric-box">
                  <span className="metric-label">Recognition Engine</span>
                  <span className="metric-value">{result.recognition?.engine || 'N/A'}</span>
                </div>
                <div className="metric-box">
                  <span className="metric-label">Processing Time</span>
                  <span className="metric-value">
                    {result.recognition?.processing_time_ms !== undefined
                      ? `${result.recognition.processing_time_ms.toFixed(1)} ms`
                      : 'N/A'}
                  </span>
                </div>
                <div className="metric-box">
                  <span className="metric-label">Mean Engine Confidence</span>
                  <span className="metric-value">
                    {formatConfidence(result.recognition?.confidence)}
                  </span>
                </div>
                <div className="metric-box">
                  <span className="metric-label">Original Dimensions</span>
                  <span className="metric-value">
                    {result.image
                      ? `${result.image.width} × ${result.image.height} px (${result.image.format}, ${result.image.mode})`
                      : 'N/A'}
                  </span>
                </div>
                <div className="metric-box">
                  <span className="metric-label">Detected Regions</span>
                  <span className="metric-value">
                    {result.recognition?.regions?.length ?? 0}
                  </span>
                </div>
              </div>

              {result.preprocessing?.operations?.length > 0 && (
                <div className="preprocessing-bar">
                  <strong>Preprocessing Applied:</strong>{' '}
                  {result.preprocessing.operations.map((op) => (
                    <span key={op} className="op-tag">{op}</span>
                  ))}
                </div>
              )}

              {result.warnings?.length > 0 && (
                <div className="warnings-box">
                  <h4>Pipeline Warnings</h4>
                  <ul>
                    {result.warnings.map((warn, idx) => (
                      <li key={idx}>{warn}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="card">
              <div className="section-header">
                <h2>3. Recognized Text</h2>
                {editableText !== (result.recognition?.text ?? '') && (
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => setEditableText(result.recognition?.text ?? '')}
                  >
                    Reset to Raw OCR Output
                  </button>
                )}
              </div>
              <p className="field-hint">
                Raw optical transcription returned by the recognition engine. You may inspect or edit the text below.
              </p>
              <textarea
                className="recognized-textarea"
                rows={6}
                value={editableText}
                onChange={(e) => setEditableText(e.target.value)}
                placeholder="No legible text regions were detected in the uploaded image."
              />
            </div>

            <div className="card">
              <h2>4. Detected Text Regions ({result.recognition?.regions?.length ?? 0})</h2>
              {result.recognition?.regions?.length > 0 ? (
                <div className="regions-table-wrapper">
                  <table className="regions-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Recognized Text</th>
                        <th>Confidence</th>
                        <th>Type</th>
                        <th>Bounding Box (x, y, w × h)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.recognition.regions.map((region) => (
                        <tr key={region.id}>
                          <td>{region.id}</td>
                          <td className="region-text-cell">{region.text}</td>
                          <td>{formatConfidence(region.confidence)}</td>
                          <td><code>{region.region_type}</code></td>
                          <td>
                            {region.bbox
                              ? `[${region.bbox.x_min}, ${region.bbox.y_min}] (${region.bbox.width} × ${region.bbox.height} px)`
                              : 'N/A'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="empty-regions-note">
                  No individual text bounding boxes were detected in this image.
                </p>
              )}

              <details style={{ marginTop: '1.5rem', textAlign: 'left' }}>
                <summary style={{ cursor: 'pointer', color: '#888', fontSize: '0.9rem' }}>
                  Inspect Raw API Response JSON
                </summary>
                <pre>{JSON.stringify(result, null, 2)}</pre>
              </details>
            </div>
          </div>
        )}
      </main>

      <footer style={{ marginTop: '4rem', color: '#666', fontSize: '0.8rem' }}>
        <p>© 2026 HACKNEX Research Division. CONFIDENCE-AWARE HANDWRITING DIGITIZATION PIPELINE (PHASE 2).</p>
      </footer>
    </div>
  )
}

export default App
