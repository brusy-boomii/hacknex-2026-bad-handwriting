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

const REVIEW_STATUS_META = {
  PENDING: {
    label: 'PENDING REVIEW',
    badgeClass: 'review-pending',
  },
  ACCEPTED: {
    label: 'ACCEPTED',
    badgeClass: 'review-accepted',
  },
  CORRECTED: {
    label: 'CORRECTED',
    badgeClass: 'review-corrected',
  },
  REJECTED: {
    label: 'CANDIDATE REJECTED',
    badgeClass: 'review-rejected',
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

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '')

function getApiUrl(endpoint) {
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`
  if (API_BASE_URL) {
    return `${API_BASE_URL}${cleanEndpoint}`
  }
  return `/api${cleanEndpoint}`
}

function formatReason(code) {
  return REASON_LABELS[code] || code.replace(/_/g, ' ')
}

function buildInitialReviews(regions) {
  const initial = {}
  for (const reg of regions) {
    const rawOcr = reg.raw_ocr ?? reg.text ?? ''
    initial[reg.id] = {
      status: reg.review_status || 'PENDING',
      finalText: reg.final_text ?? rawOcr,
      humanVerified: Boolean(reg.human_verified),
      verifiedSource: null,
      verifiedAt: null,
    }
  }
  return initial
}

function App() {
  const [systemStatus, setSystemStatus] = useState(null)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [selectedRegionId, setSelectedRegionId] = useState(null)
  const [regionDraft, setRegionDraft] = useState('')
  const [regionReviews, setRegionReviews] = useState({})
  const [showOverlay, setShowOverlay] = useState(true)
  const [error, setError] = useState(null)
  const [exportError, setExportError] = useState(null)
  const [exportMessage, setExportMessage] = useState(null)

  useEffect(() => {
    fetch(getApiUrl('/health'))
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
    setSelectedRegionId(null)
    setRegionDraft('')
    setRegionReviews({})
    setError(null)
    setExportError(null)
    setExportMessage(null)
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
    setExportError(null)
    setExportMessage(null)
    setResult(null)
    setSelectedRegionId(null)
    setRegionReviews({})

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch(getApiUrl('/analyze'), {
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
      const detectedRegions = data.uncertainty?.regions || data.recognition?.regions || []
      const initialReviews = buildInitialReviews(detectedRegions)
      setRegionReviews(initialReviews)

      const firstFlagged = detectedRegions.find(
        r => r.uncertainty_level === 'LOW' || r.uncertainty_level === 'UNREADABLE' || r.needs_review
      ) || detectedRegions[0]

      if (firstFlagged) {
        setSelectedRegionId(firstFlagged.id)
        setRegionDraft(firstFlagged.raw_ocr ?? firstFlagged.text ?? '')
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

  const getRegionReview = (region) => {
    const rawOcr = region.raw_ocr ?? region.text ?? ''
    return regionReviews[region.id] || {
      status: region.review_status || 'PENDING',
      finalText: region.final_text ?? rawOcr,
      humanVerified: Boolean(region.human_verified),
      verifiedSource: null,
      verifiedAt: null,
    }
  }

  const handleSelectRegion = (region) => {
    setSelectedRegionId(region.id)
    const currentReview = getRegionReview(region)
    setRegionDraft(currentReview.finalText)
    setExportError(null)
    setExportMessage(null)
  }

  const updateSingleRegionReview = (regionId, nextState) => {
    setRegionReviews(prev => ({
      ...prev,
      [regionId]: {
        ...prev[regionId],
        ...nextState,
        verifiedAt: new Date().toLocaleTimeString(),
      },
    }))
    setExportError(null)
    setExportMessage(null)
  }

  const handleAcceptRawOcr = (region) => {
    const rawOcr = region.raw_ocr ?? region.text ?? ''
    setRegionDraft(rawOcr)
    updateSingleRegionReview(region.id, {
      status: 'ACCEPTED',
      finalText: rawOcr,
      humanVerified: true,
      verifiedSource: 'raw_ocr',
    })
  }

  const handleAcceptCandidate = (region) => {
    const candidate = region.secondary_verification?.candidate_text
    if (!candidate) return
    setRegionDraft(candidate)
    updateSingleRegionReview(region.id, {
      status: 'ACCEPTED',
      finalText: candidate,
      humanVerified: true,
      verifiedSource: 'secondary_candidate',
    })
  }

  const handleRejectCandidate = (region) => {
    const rawOcr = region.raw_ocr ?? region.text ?? ''
    setRegionDraft(rawOcr)
    updateSingleRegionReview(region.id, {
      status: 'REJECTED',
      finalText: rawOcr,
      humanVerified: true,
      verifiedSource: 'candidate_rejected',
    })
  }

  const handleSaveManualCorrection = (region) => {
    updateSingleRegionReview(region.id, {
      status: 'CORRECTED',
      finalText: regionDraft,
      humanVerified: true,
      verifiedSource: 'manual_correction',
    })
  }

  const handleResetSingleRegion = (region) => {
    const rawOcr = region.raw_ocr ?? region.text ?? ''
    setRegionDraft(rawOcr)
    setRegionReviews(prev => ({
      ...prev,
      [region.id]: {
        status: 'PENDING',
        finalText: rawOcr,
        humanVerified: false,
        verifiedSource: null,
        verifiedAt: null,
      },
    }))
  }

  const handleAcceptAllReliableRegions = () => {
    const now = new Date().toLocaleTimeString()
    setRegionReviews(prev => {
      const next = { ...prev }
      for (const reg of regions) {
        if (reg.uncertainty_level === 'HIGH' && !reg.needs_review) {
          const rawOcr = reg.raw_ocr ?? reg.text ?? ''
          next[reg.id] = {
            status: 'ACCEPTED',
            finalText: rawOcr,
            humanVerified: true,
            verifiedSource: 'raw_ocr',
            verifiedAt: now,
          }
        }
      }
      return next
    })
  }

  const handleResetAllReviews = () => {
    const resetState = buildInitialReviews(regions)
    setRegionReviews(resetState)
    if (selectedRegion) {
      setRegionDraft(selectedRegion.raw_ocr ?? selectedRegion.text ?? '')
    }
    setExportError(null)
    setExportMessage(null)
  }

  // Provenance computations: raw OCR is never overwritten
  const rawOcrFullText = result?.raw_ocr_text ?? result?.recognition?.text ?? ''
  const finalVerifiedFullText = regions.length > 0
    ? regions.map(r => getRegionReview(r).finalText).join('\n')
    : rawOcrFullText

  const totalRegionsCount = regions.length
  const humanVerifiedCount = regions.filter(r => getRegionReview(r).humanVerified).length
  const pendingFlaggedCount = regions.filter(
    r => (r.uncertainty_level === 'LOW' || r.uncertainty_level === 'UNREADABLE' || r.needs_review) && !getRegionReview(r).humanVerified
  ).length
  const anyHumanModification = finalVerifiedFullText !== rawOcrFullText || humanVerifiedCount > 0

  const buildExportPayload = () => {
    if (!result || !result.filename) {
      throw new Error('No active analysis result available to export.')
    }
    return {
      filename: result.filename,
      engine: result.recognition?.engine || null,
      overall_uncertainty: result.uncertainty?.overall_level || null,
      regions: regions.map((r) => {
        const rev = getRegionReview(r)
        return {
          id: r.id,
          raw_ocr: r.raw_ocr ?? r.text ?? '',
          uncertainty: r.uncertainty_level || 'MEDIUM',
          needs_review: Boolean(r.needs_review),
          reasons: r.reasons || [],
          candidate_text: r.secondary_verification?.candidate_text ?? null,
          review_status: rev.status,
          final_text: rev.finalText,
          human_verified: Boolean(rev.humanVerified),
        }
      }),
      final_text: finalVerifiedFullText,
    }
  }

  const triggerBrowserDownload = (content, filename, mimeType) => {
    const blob = new Blob([content], { type: mimeType })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const handleExportJson = async () => {
    setExportError(null)
    setExportMessage(null)
    try {
      const payload = buildExportPayload()
      const response = await fetch(getApiUrl('/export/json'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        throw new Error(errData.detail || `JSON export failed with status ${response.status}`)
      }
      const exportedJson = await response.json()
      const safeBase = (result.filename || 'document').replace(/\.[^/.]+$/, '')
      const targetName = `${safeBase}_provenance.json`
      triggerBrowserDownload(
        JSON.stringify(exportedJson, null, 2),
        targetName,
        'application/json;charset=utf-8'
      )
      setExportMessage(`Exported provenance JSON: ${targetName}`)
    } catch (err) {
      setExportError(err.message || 'Failed to export JSON.')
    }
  }

  const handleExportTxt = async () => {
    setExportError(null)
    setExportMessage(null)
    try {
      const payload = buildExportPayload()
      const response = await fetch(getApiUrl('/export/txt'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) {
        const errData = await response.json().catch(() => ({}))
        throw new Error(errData.detail || `TXT export failed with status ${response.status}`)
      }
      const txtContent = await response.text()
      const safeBase = (result.filename || 'document').replace(/\.[^/.]+$/, '')
      const targetName = `${safeBase}_verified.txt`
      triggerBrowserDownload(txtContent, targetName, 'text/plain;charset=utf-8')
      setExportMessage(`Exported plain text: ${targetName}`)
    } catch (err) {
      setExportError(err.message || 'Failed to export plain text.')
    }
  }

  const uncertaintySummary = result?.uncertainty
  const verificationSummary = result?.verification
  const overallLevel = uncertaintySummary?.overall_level || 'MEDIUM'
  const overallMeta = UNCERTAINTY_META[overallLevel] || UNCERTAINTY_META.MEDIUM

  return (
    <div className="App">
      <header className="header">
        <h1>Extreme Bad-Handwriting Digitizing Stack</h1>
        <p className="subtitle">HACKNEX 2026 | Project HNX26EPS04</p>
        <p className="innovation-banner">
          &ldquo;Don&apos;t blindly trust OCR &mdash; know what needs human verification.&rdquo;
        </p>

        <div className="pipeline-stepper" aria-label="Digitization workflow stages">
          <span className={`step-pill ${file ? 'step-done' : 'step-active'}`}>1. IMAGE</span>
          <span className="step-arrow">&rarr;</span>
          <span className={`step-pill ${result ? 'step-done' : ''}`}>2. OCR</span>
          <span className="step-arrow">&rarr;</span>
          <span className={`step-pill ${result?.uncertainty ? 'step-done' : ''}`}>3. UNCERTAINTY</span>
          <span className="step-arrow">&rarr;</span>
          <span className={`step-pill ${humanVerifiedCount > 0 ? 'step-done' : (result ? 'step-active' : '')}`}>4. REVIEW</span>
          <span className="step-arrow">&rarr;</span>
          <span className={`step-pill ${exportMessage ? 'step-done' : (result ? 'step-active' : '')}`}>5. FINAL TEXT &amp; EXPORT</span>
        </div>

        {systemStatus && (
          <div style={{ marginTop: '0.85rem' }}>
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
          <h2>1. Document Ingestion &amp; Upload</h2>
          <p>Upload a handwritten document image to run validation, preprocessing, optical recognition, multi-signal uncertainty detection, and selective secondary verification.</p>

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
                <h2>2. Recognition Telemetry, Uncertainty &amp; Selective Verification</h2>
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
                <div className="metric-box">
                  <span className="metric-label">Secondary Verification Status</span>
                  <span className="metric-value">
                    {verificationSummary?.status || 'secondary verification unavailable'}
                  </span>
                </div>
              </div>

              {verificationSummary && (
                <div className="verification-summary-bar">
                  <strong>Selective Secondary Verification (Phase 4A):</strong>{' '}
                  <span>
                    Routed <strong>{verificationSummary.verified_region_count}</strong> uncertain region(s)
                    (<code>LOW</code> / <code>UNREADABLE</code> / <code>needs_review</code>), skipped{' '}
                    <strong>{verificationSummary.skipped_region_count}</strong> reliable <code>HIGH</code> region(s).
                    Status: <code>{verificationSummary.status}</code>.
                  </span>
                </div>
              )}

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
                  <h4>Pipeline &amp; Uncertainty Warnings</h4>
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
                  <h2>3. Visual Uncertainty Overlay &amp; Region Map</h2>
                  <button
                    type="button"
                    className="secondary-btn"
                    onClick={() => setShowOverlay(!showOverlay)}
                  >
                    {showOverlay ? 'Hide Bounding Boxes' : 'Show Bounding Boxes'}
                  </button>
                </div>
                <p className="field-hint">
                  Bounding boxes are rendered in original image coordinates ({result.image.width} &times; {result.image.height} px). Click any region box to inspect its reliability evidence and human-review controls.
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
                <h2>4. Human-in-the-Loop Uncertainty Review Workflow</h2>
                <div className="badge-group">
                  <span className="review-progress-pill">
                    Reviewed: {humanVerifiedCount} / {totalRegionsCount} region(s)
                  </span>
                  {pendingFlaggedCount > 0 && (
                    <span className="status-badge status-loading">
                      {pendingFlaggedCount} Flagged Region(s) Pending Review
                    </span>
                  )}
                  {regions.some(r => r.uncertainty_level === 'HIGH' && !r.needs_review) && (
                    <button
                      type="button"
                      className="secondary-btn"
                      onClick={handleAcceptAllReliableRegions}
                    >
                      Accept All Reliable (HIGH) Regions
                    </button>
                  )}
                  {anyHumanModification && (
                    <button
                      type="button"
                      className="secondary-btn"
                      onClick={handleResetAllReviews}
                    >
                      Reset All Reviews to PENDING
                    </button>
                  )}
                </div>
              </div>
              <p className="field-hint">
                Reliable OCR regions can be accepted efficiently, while <code>LOW</code> and <code>UNREADABLE</code> regions are highlighted for human verification. Raw OCR is never overwritten.
              </p>

              {regions.length > 0 ? (
                <div className="uncertainty-lines-list">
                  {regions.map((region) => {
                    const tier = region.uncertainty_level || 'MEDIUM'
                    const meta = UNCERTAINTY_META[tier] || UNCERTAINTY_META.MEDIUM
                    const rev = getRegionReview(region)
                    const revMeta = REVIEW_STATUS_META[rev.status] || REVIEW_STATUS_META.PENDING
                    const rawOcr = region.raw_ocr ?? region.text ?? ''
                    const displayText = rev.finalText
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
                            [{meta.shortLabel}]
                          </span>
                          <span className={`review-status-badge ${revMeta.badgeClass}`}>
                            {revMeta.label}
                          </span>
                        </div>
                        <div className="region-row-text">
                          {tier === 'HIGH' || rev.humanVerified ? (
                            <span className="reliable-text">&ldquo;{displayText}&rdquo;</span>
                          ) : (
                            <span className="uncertain-text">
                              &ldquo;[{displayText || 'UNREADABLE'}?]&rdquo;
                            </span>
                          )}
                          {rev.finalText !== rawOcr && (
                            <span className="raw-diff-note">
                              {' '}(Raw OCR: &ldquo;{rawOcr}&rdquo;)
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

              {selectedRegion && (() => {
                const selectedReview = getRegionReview(selectedRegion)
                const selectedReviewMeta = REVIEW_STATUS_META[selectedReview.status] || REVIEW_STATUS_META.PENDING
                const sv = selectedRegion.secondary_verification
                const rawOcr = selectedRegion.raw_ocr ?? selectedRegion.text ?? ''
                const candidateText = sv?.candidate_text ?? null

                return (
                  <div className="inspector-panel">
                    <div className="section-header">
                      <h3>
                        Region #{selectedRegion.id} Inspector &amp; Human Verification
                      </h3>
                      <div className="badge-group">
                        <span className={`uncertainty-badge ${(UNCERTAINTY_META[selectedRegion.uncertainty_level] || UNCERTAINTY_META.MEDIUM).badgeClass}`}>
                          Uncertainty: {selectedRegion.uncertainty_level}
                        </span>
                        <span className={`review-status-badge ${selectedReviewMeta.badgeClass}`}>
                          Review Status: {selectedReview.status}
                        </span>
                      </div>
                    </div>

                    <div className="inspector-grid">
                      <div>
                        <p className="inspector-kv">
                          <strong>Original Raw OCR Text (Immutable):</strong>{' '}
                          <code>{rawOcr || '(empty)'}</code>
                        </p>
                        <p className="inspector-kv">
                          <strong>Current Final Text:</strong>{' '}
                          <code>{selectedReview.finalText || '(empty)'}</code>
                          {selectedReview.humanVerified && (
                            <span className="verified-inline-tag">
                              {' '}✓ Human Verified ({selectedReview.status})
                            </span>
                          )}
                        </p>
                        <p className="inspector-kv">
                          <strong>Raw OCR Confidence:</strong> {formatConfidence(selectedRegion.ocr_confidence ?? selectedRegion.confidence)}
                          {' '}| <strong>Calibrated Score:</strong> {formatConfidence(selectedRegion.normalized_confidence)}
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
                          <strong>Flagged Uncertainty Reasons:</strong>{' '}
                          {selectedRegion.reasons?.length > 0 ? (
                            <ul>
                              {selectedRegion.reasons.map((rCode) => (
                                <li key={rCode}>
                                  <code>{rCode}</code> &mdash; {formatReason(rCode)}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <span>None (all optical, contrast, sharpness, and plausibility checks passed).</span>
                          )}
                        </div>

                        <div className="secondary-verification-box">
                          <strong>Secondary Verification (Phase 4A):</strong>
                          {sv ? (
                            <div className="sv-details">
                              <p className="inspector-kv">
                                <span>Status: <code>{sv.status}</code></span>
                                {sv.attempted ? ' (Triggered selectively for review region)' : ' (Skipped: reliable OCR region)'}
                              </p>
                              {candidateText ? (
                                <p className="inspector-kv">
                                  <strong>Secondary Candidate:</strong>{' '}
                                  <code className="candidate-highlight">{candidateText}</code>
                                  {sv.confidence !== null && sv.confidence !== undefined && (
                                    <span> (Confidence: {formatConfidence(sv.confidence)})</span>
                                  )}
                                </p>
                              ) : (
                                <p className="inspector-kv">
                                  <strong>Secondary Candidate:</strong> <code>null</code> &mdash;{' '}
                                  {sv.status === 'secondary verification unavailable'
                                    ? 'secondary verification unavailable (original OCR preserved; manual review required)'
                                    : sv.message || 'No secondary candidate produced.'}
                                </p>
                              )}
                            </div>
                          ) : (
                            <p className="inspector-kv">secondary verification unavailable</p>
                          )}
                        </div>
                      </div>

                      <div className="inspector-editor">
                        <label htmlFor="regionCorrectionInput">
                          <strong>Human Review Actions for Region #{selectedRegion.id}:</strong>
                        </label>
                        <div className="quick-review-actions">
                          <button
                            type="button"
                            className="secondary-btn action-accept-ocr"
                            onClick={() => handleAcceptRawOcr(selectedRegion)}
                          >
                            Accept Raw OCR (&ldquo;{rawOcr || 'empty'}&rdquo;)
                          </button>
                          {candidateText && (
                            <>
                              <button
                                type="button"
                                className="secondary-btn action-accept-candidate"
                                onClick={() => handleAcceptCandidate(selectedRegion)}
                              >
                                Accept Candidate (&ldquo;{candidateText}&rdquo;)
                              </button>
                              <button
                                type="button"
                                className="secondary-btn action-reject-candidate"
                                onClick={() => handleRejectCandidate(selectedRegion)}
                              >
                                Reject Candidate
                              </button>
                            </>
                          )}
                        </div>

                        <label htmlFor="regionCorrectionInput" style={{ marginTop: '0.5rem', fontSize: '0.86rem' }}>
                          Or Manually Correct Transcription:
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
                            onClick={() => handleSaveManualCorrection(selectedRegion)}
                          >
                            Save Manual Correction (Mark CORRECTED)
                          </button>
                          {selectedReview.status !== 'PENDING' && (
                            <button
                              type="button"
                              className="secondary-btn"
                              onClick={() => handleResetSingleRegion(selectedRegion)}
                            >
                              Reset Region to PENDING
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })()}
            </div>

            <div className="card">
              <div className="section-header">
                <h2>5. Final Transcription, Provenance &amp; Export</h2>
                <div className="badge-group">
                  <button
                    type="button"
                    className="primary-btn small-btn"
                    onClick={handleExportTxt}
                  >
                    Export Plain Text (.txt)
                  </button>
                  <button
                    type="button"
                    className="secondary-btn export-json-btn"
                    onClick={handleExportJson}
                  >
                    Export Provenance JSON (.json)
                  </button>
                </div>
              </div>
              <p className="field-hint">
                Provenance is strictly preserved: the original <strong>RAW OCR OUTPUT</strong> is never overwritten, and <strong>HUMAN-VERIFIED OUTPUT</strong> is tracked separately for downstream auditability.
              </p>

              {exportError && (
                <div className="warnings-box" style={{ borderLeftColor: '#e53935' }}>
                  <h4 style={{ color: '#ff8a80' }}>Export Error</h4>
                  <p style={{ margin: 0, fontSize: '0.88rem' }}>{exportError}</p>
                </div>
              )}

              {exportMessage && (
                <div className="export-success-banner">
                  {exportMessage}
                </div>
              )}

              <div className="provenance-comparison-grid">
                <div className="provenance-column">
                  <div className="provenance-col-header">
                    <span className="provenance-tag raw-tag">RAW OCR OUTPUT (UNMODIFIED)</span>
                    <span className="provenance-sub">Source: {result.recognition?.engine || 'PP-OCRv3'}</span>
                  </div>
                  <pre className="provenance-text-box">{rawOcrFullText || '(No text detected)'}</pre>
                </div>

                <div className="provenance-column">
                  <div className="provenance-col-header">
                    <span className={`provenance-tag ${anyHumanModification ? 'verified-tag' : 'pending-tag'}`}>
                      {anyHumanModification
                        ? 'HUMAN-VERIFIED OUTPUT'
                        : 'FINAL OUTPUT (AWAITING HUMAN VERIFICATION)'}
                    </span>
                    <span className="provenance-sub">
                      {humanVerifiedCount} of {totalRegionsCount} region(s) verified
                    </span>
                  </div>
                  <pre className="provenance-text-box verified-text-box">
                    {finalVerifiedFullText || '(No text detected)'}
                  </pre>
                </div>
              </div>
            </div>

            <div className="card">
              <h2>6. Region-Level Provenance &amp; Telemetry Table ({regions.length})</h2>
              {regions.length > 0 ? (
                <div className="regions-table-wrapper">
                  <table className="regions-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Raw OCR (Immutable)</th>
                        <th>Final Verified Text</th>
                        <th>Uncertainty</th>
                        <th>Review Status</th>
                        <th>Secondary Verification</th>
                        <th>Raw Conf</th>
                        <th>Calibrated</th>
                        <th>Reasons</th>
                      </tr>
                    </thead>
                    <tbody>
                      {regions.map((region) => {
                        const tier = region.uncertainty_level || 'MEDIUM'
                        const meta = UNCERTAINTY_META[tier] || UNCERTAINTY_META.MEDIUM
                        const rev = getRegionReview(region)
                        const revMeta = REVIEW_STATUS_META[rev.status] || REVIEW_STATUS_META.PENDING
                        const rawOcr = region.raw_ocr ?? region.text ?? ''
                        const sv = region.secondary_verification
                        return (
                          <tr
                            key={region.id}
                            className={region.id === selectedRegionId ? 'selected-table-row' : ''}
                            onClick={() => handleSelectRegion(region)}
                            style={{ cursor: 'pointer' }}
                          >
                            <td>{region.id}</td>
                            <td className="region-text-cell">{rawOcr}</td>
                            <td className="region-text-cell">{rev.finalText}</td>
                            <td>
                              <span className={`uncertainty-badge ${meta.badgeClass}`}>
                                {tier}
                              </span>
                            </td>
                            <td>
                              <span className={`review-status-badge ${revMeta.badgeClass}`}>
                                {rev.status}
                              </span>
                            </td>
                            <td>
                              {sv?.candidate_text
                                ? `Candidate: "${sv.candidate_text}"`
                                : (sv?.status || 'N/A')}
                            </td>
                            <td>{formatConfidence(region.ocr_confidence ?? region.confidence)}</td>
                            <td>{formatConfidence(region.normalized_confidence)}</td>
                            <td>
                              {region.reasons?.length > 0
                                ? region.reasons.join(', ')
                                : 'none'}
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
        <p>&copy; 2026 HACKNEX Research Division. CONFIDENCE-AWARE HANDWRITING DIGITIZATION PIPELINE (PHASE 4).</p>
      </footer>
    </div>
  )
}

export default App
