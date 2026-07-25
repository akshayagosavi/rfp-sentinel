import { useCallback, useState } from 'react'
import { UploadCloud, FileText, X } from 'lucide-react'

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function RfpUploadForm({ onSubmit }) {
  const [file, setFile] = useState(null)
  const [dragOver, setDragOver] = useState(false)

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    const dropped = e.dataTransfer.files?.[0]
    if (dropped) setFile(dropped)
  }, [])

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`flex flex-col items-center justify-center rounded-card border-2 border-dashed px-6 py-16 text-center transition-all duration-200 ${
          dragOver
            ? 'border-accent bg-accent/5 scale-[1.01]'
            : 'border-line bg-surface hover:border-accent/50 hover:bg-accent/5'
        }`}
      >
        {file ? (
          <div className="flex items-center gap-3 rounded-full border border-line bg-elevated px-4 py-2 text-sm text-ink shadow-sm">
            <FileText size={16} className="shrink-0 text-accent" />
            <span className="max-w-[16rem] truncate">{file.name}</span>
            <span className="shrink-0 text-xs text-subtle">{formatFileSize(file.size)}</span>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                setFile(null)
              }}
              aria-label="Remove file"
              className="ml-1 shrink-0 rounded-full p-1 text-subtle transition-colors duration-200 hover:bg-danger-soft hover:text-danger"
            >
              <X size={14} />
            </button>
          </div>
        ) : (
          <>
            <UploadCloud size={28} className="text-subtle" />
            <p className="mt-3 text-sm text-ink">Drag and drop your RFP PDF here, or</p>
            <label className="mt-3 cursor-pointer text-sm font-medium text-accent transition-colors duration-200 hover:text-accent-hover">
              browse files
              <input
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
          </>
        )}
      </div>

      <button
        onClick={() => file && onSubmit(file)}
        disabled={!file}
        className={`mt-6 w-full rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 ${
          file
            ? 'bg-accent text-white hover:scale-[1.01] hover:bg-accent-hover hover:shadow-[0_0_20px_-6px_var(--color-accent)]'
            : 'cursor-not-allowed border border-line bg-surface text-subtle'
        }`}
      >
        Submit for evaluation
      </button>
    </div>
  )
}
