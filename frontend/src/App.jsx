import { useState, useEffect } from 'react'
import './index.css'

const UNCERTAINTY_META = {
  HIGH: {
    label: 'HIGH RELIABILITY',
    shortLabel: 'HIGH',
    badgeClass: 'tier-high',
    stroke: '#43a047',
    fill: 'rgba(67, 160, 71, 0.14)',
    description: 'Strong OCR confidence and acceptable local image/text quality.',
  },
  MEDIUM: {
    label: 'MEDIUM (REVIEW SUGGESTED)',
    shortLabel: 'MEDIUM',
    badgeClass: 'tier-medium',
    stroke: '#fbc02d',
    fill: 'rgba(251, 192, 45, 0.16)',
    description: 'Usable recognition, but one or more warning signals detected.',
  },
  LOW: {
    label: 'LOW CONFIDENCE',
    shortLabel: 'LOW',
    badgeClass: 'tier-low',
    stroke: '#fb8c00',
    fill: 'rgba(251, 140, 0, 0.20)',
    description: 'Weak OCR confidence or significant image quality/plausibility concerns.',
  },
  UNREADABLE: {
    label: 'UNREADABLE / UNTRUSTWORTHY',
    shortLabel: 'UNREADABLE',
    badgeClass: 'tier-unreadable',
    stroke: '#e53935',
    fill: 'rgba(229, 57, 53, 0.24)',
    description: 'Insufficient optical or structural evidence for trustworthy recognition.',
  },
}

const REASON_LABELS = {
  moderate_ocr_confidence: 'Moderate OCR engine confidence',
  low_ocr_confidence: 'Low OCR engine confidence (< 60%)',
  very_low_ocr_confidence: 'Very low OCR engine confidence (< 35%)',
  missing_ocr_confidence: 'OCR engine confidence unavailable',
  low_local_contrast: 'Low local foreground/background contrast',
  blurry_region: 'Blurry region (low Laplacian edge variance)',
  faint_stroke_visibility: 'Faint ink stroke visibility',
  saturated_or_heavily_crossed_region: 'Heavily saturated / crossed-out stroke density',
  excessive_image_noise: 'Elevated high-frequency image grain/noise',
  tiny_region_dimensions: 'Very small bounding box dimensions',
  abnormal_region_aspect_ratio: 'Abnormal region aspect ratio',
  detector_fallback_region: 'Single-line detector fallback used',
  missing_or_degenerate_bbox: 'Missing or degenerate bounding box',
  empty_ocr_text: 'Empty OCR transcription',
  single_punctuation_fragment: 'Single isolated punctuation fragment',
  very_short_ocr_token: 'Very short single-character token',
  non_alphanumeric_only: 'Contains only non-alphanumeric symbols',
  excessive_non_alphanumeric_symbols: 'High ratio of non-alphanumeric symbols',
  elevated_symbol_noise: 'Elevated punctuation/symbol noise',
  suspicious_repeated_characters: 'Suspicious repeated character sequence',
  width_text_length_mismatch: 'Region width inconsistent with short recognized text',
  cramped_character_density: 'Cramped horizontal character density',
  no_text_regions_detected: 'No legible text regions detected on page',
}

function formatReason(code) {
  return REASON_LABELS[code] || code.replace(/_/g, ' ')
}

function App() {
  const [systemStatus, setSystemStatus] = useState(null)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [editableText, setEditableText] = useState('')
  const [selectedRegionId, setSelectedRegionId] = useState(null)
  const [regionDraft, setRegionDraft] = useState('')
  const [regionOverrides, setRegionOverrides] = useState({})
  const [showOverlay, setShowOverlay] = useState(true)
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
    setSelectedRegionId(null)
    setRegionDraft('')
    setRegionOverrides({})
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
    setSelectedRegionId(null)
    setRegionOverrides({})

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

      const regions = data.uncertainty?.regions || data.recognition?.regions || []
      const firstFlagged = regions.find(r => r.needs_review) || regions[0]
      if (firstFlagged) {
        setSelectedRegionId(firstFlagged.id)
        setRegionDraft(firstFlagged.text || '')
      }
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

  const regions = result?.uncertainty?.regions || result?.recognition?.regions || []
  const selectedRegion = regions.find(r => r.id === selectedRegionId) || null

  const handleSelectRegion = (region) => {
    setSelectedRegionId(region.id)
    const existingOverride = regionOverrides[region.id]
    setRegionDraft(existingOverride ? existingOverride.text : (region.text || ''))
  }

  const handleSaveRegionCorrection = (regionId) => {
    const updatedOverrides = {
      ...regionOverrides,
      [regionId]: {
        text: regionDraft,
        verifiedAt: new Date().toLocaleTimeString(),
      },
    }
    setRegionOverrides(updatedOverrides)

    const mergedLines = regions.map(r => {
      if (updatedOverrides[r.id] !== undefined) {
        return updatedOverrides[r.id].text
      }
      return r.text
    })
    setEditableText(mergedLines.join('\n'))
  }

  const handleResetRegionCorrection = (regionId, rawText) => {
    const nextOverrides = { ...regionOverrides }
    delete nextOverrides[regionId]
    setRegionOverrides(nextOverrides)
    setRegionDraft(rawText || '')

    const mergedLines = regions.map(r => {
      if (nextOverrides[r.id] !== undefined) {
        return nextOverrides[r.id].text
      }
      return r.text
    })
    setEditableText(mergedLines.join('\n'))
  }

  const uncertaintySummary = result?.uncertainty
  const overallLevel = uncertaintySummary?.overall_level || 'MEDIUM'
  const overallMeta = UNCERTAINTY_META[overallLevel] || UNCERTAINTY_META.MEDIUM

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
          <p>Upload a handwritten document image to run validation, preprocessing, optical recognition, and multi-signal uncertainty detection.</p>

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
              {isAnalyzing ? 'Running Recognition & Uncertainty Pipeline...' : 'Run Digitization Analysis'}
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
                <h2>2. Recognition Telemetry & Uncertainty Summary</h2>
                <div className="badge-group">
                  <span className={`uncertainty-badge ${overallMeta.badgeClass}`}>
                    Overall: {overallMeta.label}
                  </span>
                  {uncertaintySummary?.review_recommended ? (
                    <span className="status-badge status-loading">Human Review Recommended</span>
                  ) : (
                    <span className="status-badge status-healthy">No Review Required</span>
                  )}
                </div>
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
                  <span className="metric-label">Mean Raw OCR Confidence</span>
                  <span className="metric-value">
                    {formatConfidence(result.recognition?.confidence)}
                  </span>
                </div>
                <div className="metric-box">
                  <span className="metric-label">Mean Calibrated Reliability</span>
                  <span className="metric-value">
                    {formatConfidence(uncertaintySummary?.mean_normalized_confidence)}
                  </span>
                </div>
                <div className="metric-box">
                  <span className="metric-label">Flagged for Review</span>
                  <span className="metric-value">
                    {uncertaintySummary
                      ? `${uncertaintySummary.flagged_region_count} / ${uncertaintySummary.total_regions} region(s)`
                      : '0'}
                  </span>
                </div>
              </div>

              {uncertaintySummary?.counts && (
                <div className="tier-counts-grid">
                  {(['HIGH', 'MEDIUM', 'LOW', 'UNREADABLE']).map((tier) => {
                    const meta = UNCERTAINTY_META[tier]
                    const count = uncertaintySummary.counts[tier] ?? 0
                    return (
                      <div key={tier} className={`tier-count-card ${meta.badgeClass}`}>
                        <span className="tier-count-number">{count}</span>
                        <span className="tier-count-label">{meta.shortLabel}</span>
                      </div>
                    )
                  })}
                </div>
              )}

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
                  <h4>Pipeline & Uncertainty Warnings</h4>
                  <ul>
                    {result.warnings.map((warn, idx) => (
                      <li key={idx}>{warn}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {preview && result.image && (
              <div className="card">
                <div className="section-header">
                  <h2>3. Visual Uncertainty Overlay & Region Map</h2>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => setShowOverlay(!showOverlay)}
                  >
                    {showOverlay ? 'Hide Bounding Boxes' : 'Show Bounding Boxes'}
                  </button>
                </div>
                <p className="field-hint">
                  Bounding boxes are rendered in original image coordinates ({result.image.width} × {result.image.height} px). Click any region box to inspect its reliability evidence and human-review controls.
                </p>

                <div className="legend-bar">
                  {(['HIGH', 'MEDIUM', 'LOW', 'UNREADABLE']).map((tier) => {
                    const meta = UNCERTAINTY_META[tier]
                    return (
                      <span key={tier} className="legend-item">
                        <span className={`uncertainty-badge ${meta.badgeClass}`}>{meta.shortLabel}</span>
                        <span className="legend-desc">{meta.description}</span>
                      </span>
                    )
                  })}
                </div>

                <div className="overlay-stage-wrapper">
                  <div className="overlay-stage">
                    <img
                      src={preview}
                      alt="Original document with region overlays"
                      className="overlay-base-image"
                    />
                    {showOverlay && regions.length > 0 && (
                      <svg
                        className="bbox-overlay-svg"
                        viewBox={`0 0 ${result.image.width} ${result.image.height}`}
                        preserveAspectRatio="none"
                      >
                        {regions.map((region) => {
                          if (!region.bbox) return null
                          const tier = region.uncertainty_level || 'MEDIUM'
                          const meta = UNCERTAINTY_META[tier] || UNCERTAINTY_META.MEDIUM
                          const isSelected = region.id === selectedRegionId
                          const labelY = Math.max(14, region.bbox.y_min - 4)
                          return (
                            <g
                              key={region.id}
                              className="bbox-group"
                              onClick={() => handleSelectRegion(region)}
                            >
                              <rect
                                x={region.bbox.x_min}
                                y={region.bbox.y_min}
                                width={region.bbox.width}
                                height={region.bbox.height}
                                fill={meta.fill}
                                stroke={meta.stroke}
                                strokeWidth={isSelected ? 3.5 : 2}
                                strokeDasharray={tier === 'LOW' || tier === 'UNREADABLE' ? '5,3' : undefined}
                              />
                              <text
                                x={region.bbox.x_min + 2}
                                y={labelY}
                                fill={meta.stroke}
                                fontSize="12"
                                fontWeight="bold"
                                className="svg-region-label"
                              >
                                #{region.id} [{meta.shortLabel}]
                              </text>
                            </g>
                          )
                        })}
                      </svg>
                    )}
                  </div>
                </div>
              </div>
            )}

            <div className="card">
              <div className="section-header">
                <h2>4. Uncertainty-Aware Transcription & Human Review</h2>
                {editableText !== (result.recognition?.text ?? '') && (
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => {
                      setRegionOverrides({})
                      setEditableText(result.recognition?.text ?? '')
                      if (selectedRegion) {
                        setRegionDraft(selectedRegion.text || '')
                      }
                    }}
                  >
                    Reset All to Raw OCR Output
                  </button>
                )}
              </div>
              <p className="field-hint">
                Uncertain regions are explicitly flagged below rather than silently altered. Click any region chip to inspect its quality indicators or record a manual correction.
              </p>

              {regions.length > 0 ? (
                <div className="uncertainty-lines-list">
                  {regions.map((region) => {
                    const tier = region.uncertainty_level || 'MEDIUM'
                    const meta = UNCERTAINTY_META[tier] || UNCERTAINTY_META.MEDIUM
                    const override = regionOverrides[region.id]
                    const displayText = override ? override.text : region.text
                    const isSelected = region.id === selectedRegionId

                    return (
                      <div
                        key={region.id}
                        className={`transcription-region-row ${isSelected ? 'selected-row' : ''}`}
                        onClick={() => handleSelectRegion(region)}
                      >
                        <div className="region-row-left">
                          <span className="region-index-tag">#{region.id}</span>
                          <span className={`uncertainty-badge ${meta.badgeClass}`}>
                            [{meta.shortLabel} CONFIDENCE]
                          </span>
                          {override && (
                            <span className="verified-pill">HUMAN EDITED ({override.verifiedAt})</span>
                          )}
                        </div>
                        <div className="region-row-text">
                          {tier === 'HIGH' || override ? (
                            <span className="reliable-text">&ldquo;{displayText}&rdquo;</span>
                          ) : (
                            <span className="uncertain-text">
                              &ldquo;[{displayText || 'UNREADABLE'}?]&rdquo;
                            </span>
                          )}
                        </div>
                        <div className="region-row-reasons">
                          {region.reasons?.length > 0 ? (
                            region.reasons.map((rCode) => (
                              <span key={rCode} className="reason-pill" title={formatReason(rCode)}>
                                {rCode}
                              </span>
                            ))
                          ) : (
                            <span className="reason-pill reason-clean">verified_clean_signals</span>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="empty-regions-note">
                  No legible text regions were detected in the uploaded image.
                </p>
              )}

              {selectedRegion && (
                <div className="inspector-panel">
                  <div className="section-header">
                    <h3>
                      Region #{selectedRegion.id} Inspector &amp; Manual Review
                    </h3>
                    <span className={`uncertainty-badge ${(UNCERTAINTY_META[selectedRegion.uncertainty_level] || UNCERTAINTY_META.MEDIUM).badgeClass}`}>
                      [{selectedRegion.uncertainty_level}] {selectedRegion.needs_review ? '— Needs Human Review' : '— Reliable'}
                    </span>
                  </div>

                  <div className="inspector-grid">
                    <div>
                      <p className="inspector-kv">
                        <strong>Raw OCR Text:</strong> <code>{selectedRegion.text || '(empty)'}</code>
                      </p>
                      <p className="inspector-kv">
                        <strong>Raw OCR Confidence:</strong> {formatConfidence(selectedRegion.ocr_confidence ?? selectedRegion.confidence)}
                      </p>
                      <p className="inspector-kv">
                        <strong>Calibrated Reliability Score:</strong> {formatConfidence(selectedRegion.normalized_confidence)}
                      </p>
                      {selectedRegion.quality_indicators && (
                        <p className="inspector-kv">
                          <strong>Local Image Quality:</strong>{' '}
                          {(selectedRegion.quality_indicators.image_quality_score * 100).toFixed(1)}%
                          {' '}(Sharpness Var: {selectedRegion.quality_indicators.laplacian_variance},
                          Contrast Range: {selectedRegion.quality_indicators.dynamic_range},
                          Plausibility: {(selectedRegion.quality_indicators.plausibility_score * 100).toFixed(0)}%)
                        </p>
                      )}
                      <div className="inspector-reasons">
                        <strong>Flagged Reasons:</strong>{' '}
                        {selectedRegion.reasons?.length > 0 ? (
                          <ul>
                            {selectedRegion.reasons.map((rCode) => (
                              <li key={rCode}>
                                <code>{rCode}</code> — {formatReason(rCode)}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <span>None (all optical, contrast, sharpness, and plausibility checks passed).</span>
                        )}
                      </div>
                    </div>

                    <div className="inspector-editor">
                      <label htmlFor="regionCorrectionInput">
                        <strong>Human Review / Manual Correction for Region #{selectedRegion.id}:</strong>
                      </label>
                      <input
                        id="regionCorrectionInput"
                        type="text"
                        className="region-correction-input"
                        value={regionDraft}
                        onChange={(e) => setRegionDraft(e.target.value)}
                        placeholder="Enter verified transcription for this region..."
                      />
                      <div className="inspector-actions">
                        <button
                          type="button"
                          className="primary-btn small-btn"
                          onClick={() => handleSaveRegionCorrection(selectedRegion.id)}
                        >
                          Save Region Correction
                        </button>
                        {regionOverrides[selectedRegion.id] && (
                          <button
                            type="button"
                            className="secondary-btn"
                            onClick={() => handleResetRegionCorrection(selectedRegion.id, selectedRegion.text)}
                          >
                            Revert to Raw OCR
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              <div style={{ marginTop: '1.25rem' }}>
                <label htmlFor="fullTextOutput" style={{ display: 'block', marginBottom: '0.4rem', fontWeight: 600 }}>
                  Full Document Transcription (Editable):
                </label>
                <textarea
                  id="fullTextOutput"
                  className="recognized-textarea"
                  rows={5}
                  value={editableText}
                  onChange={(e) => setEditableText(e.target.value)}
                  placeholder="No legible text regions were detected in the uploaded image."
                />
              </div>
            </div>

            <div className="card">
              <h2>5. Region-Level Telemetry Table ({regions.length})</h2>
              {regions.length > 0 ? (
                <div className="regions-table-wrapper">
                  <table className="regions-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Recognized Text</th>
                        <th>Uncertainty Level</th>
                        <th>Raw OCR Conf</th>
                        <th>Calibrated Score</th>
                        <th>Img Quality</th>
                        <th>Needs Review</th>
                        <th>Reasons</th>
                        <th>Bounding Box</th>
                      </tr>
                    </thead>
                    <tbody>
                      {regions.map((region) => {
                        const tier = region.uncertainty_level || 'MEDIUM'
                        const meta = UNCERTAINTY_META[tier] || UNCERTAINTY_META.MEDIUM
                        return (
                          <tr
                            key={region.id}
                            className={region.id === selectedRegionId ? 'selected-table-row' : ''}
                            onClick={() => handleSelectRegion(region)}
                            style={{ cursor: 'pointer' }}
                          >
                            <td>{region.id}</td>
                            <td className="region-text-cell">{region.text}</td>
                            <td>
                              <span className={`uncertainty-badge ${meta.badgeClass}`}>
                                {tier}
                              </span>
                            </td>
                            <td>{formatConfidence(region.ocr_confidence ?? region.confidence)}</td>
                            <td>{formatConfidence(region.normalized_confidence)}</td>
                            <td>
                              {region.quality_indicators
                                ? `${(region.quality_indicators.image_quality_score * 100).toFixed(0)}%`
                                : 'N/A'}
                            </td>
                            <td>{region.needs_review ? 'Yes' : 'No'}</td>
                            <td>
                              {region.reasons?.length > 0
                                ? region.reasons.join(', ')
                                : 'none'}
                            </td>
                            <td>
                              {region.bbox
                                ? `[${region.bbox.x_min}, ${region.bbox.y_min}, ${region.bbox.x_max}, ${region.bbox.y_max}]`
                                : 'N/A'}
                            </td>
                          </tr>
                        )
                      })}
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
        <p>© 2026 HACKNEX Research Division. CONFIDENCE-AWARE HANDWRITING DIGITIZATION PIPELINE (PHASE 3).</p>
      </footer>
    </div>
  )
}

export default App
