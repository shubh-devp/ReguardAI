// Reads a document in the browser and returns its text.
//
// The file is never uploaded. pdf.js runs on the page, so the only thing that
// reaches the audit API is the text the user leaves in the textarea.
//
// Text extraction is lossy: PDFs store glyphs and positions rather than words,
// so paragraph breaks and hyphenated line wraps do not survive. That is fine
// here, because the text is reviewed before it is submitted.

import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

// The parser runs in a worker so a large PDF does not block the interface.
pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

/** @param {File} file */
async function readPdf(file) {
  const document = await pdfjs.getDocument({ data: await file.arrayBuffer() }).promise

  const pages = []
  for (let number = 1; number <= document.numPages; number += 1) {
    const page = await document.getPage(number)
    const content = await page.getTextContent()
    pages.push(content.items.map((item) => item.str).join(' '))
  }

  return {
    pages: document.numPages,
    text: pages.join('\n\n').replace(/[ \t]+/g, ' ').trim(),
  }
}

/**
 * Reads a PDF or a plain text file.
 *
 * @param {File} file
 * @returns {Promise<{ text: string, note: string }>}
 */
export async function readDocument(file) {
  const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')

  if (!isPdf) {
    return { text: (await file.text()).trim(), note: 'read as plain text' }
  }

  const { text, pages } = await readPdf(file)
  return { text, note: `${pages} page${pages === 1 ? '' : 's'} extracted` }
}
