import { useState, useEffect } from 'react'
import './index.css'

function App() {
  const [systemStatus, setSystemStatus] = useState(null)
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [isDragging, setIsDragging] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/health')
      .then(res => res.json())
      .then(data => setSystemStatus(data))
      .catch(err => {
        console.error("Health check failed:", err)
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
    } catch (err) {
      setError(err.message)
    } finally {
      setIsAnalyzing(false)
    }
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
            <span style={{ marginLeft: '1rem', color: '#666', fontSize: '0.9rem' }}>
              Phase: {systemStatus.phase || 'N/A'} | {systemStatus.description}
            </span>
          </div>
        )}
      </header>

      <main>
        <div className="card">
          <h2>Document Analysis Engine</h2>
          <p>Upload a high-resolution image of handwritten text for digitization analysis.</p>
          
          <div
            className={`upload-section ${isDragging ? 'dragging' : ''}`}
            onClick={() => document.getElementById('fileInput').click()}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            {preview ? (
              <img src={preview} alt="Preview" style={{ maxWidth: '100%', maxHeight: '300px', borderRadius: '4px' }} />
            ) : (
              <div style={{ padding: '2rem' }}>
                <p>{file ? `Selected: ${file.name}` : 'Click to select or drag and drop image'}</p>
                <p style={{ fontSize: '0.8rem', color: '#666' }}>Supported: PNG, JPG, JPEG, TIFF, BMP (Max 10MB)</p>
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
              style={{ padding: '0.8rem 2rem', fontSize: '1.1rem' }}
            >
              {isAnalyzing ? 'Analyzing Pipeline...' : 'Run Analysis'}
            </button>
          </div>
        </div>

        {error && (
          <div className="card" style={{ borderLeft: '4px solid #d32f2f' }}>
            <h3 style={{ color: '#d32f2f', margin: 0 }}>Error</h3>
            <p>{error}</p>
          </div>
        )}

        {result && (
          <div className="card">
            <h3 style={{ margin: 0, color: '#4caf50' }}>Analysis Report</h3>
            <p>{result.message}</p>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </div>
        )}
      </main>

      <footer style={{ marginTop: '4rem', color: '#555', fontSize: '0.8rem' }}>
        <p>© 2026 HACKNEX Research Division. CONFIDENCE-AWARE HANDWRITING DIGITIZATION FOUNDATION.</p>
      </footer>
    </div>
  )
}

export default App
