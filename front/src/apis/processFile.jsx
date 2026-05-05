import * as pdfjsLib from "pdfjs-dist";
import pdfjsWorkerUrl from "pdfjs-dist/build/pdf.worker.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorkerUrl;

async function extractPdfText(file) {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
  const pages = [];
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    const pageText = content.items.map((item) => item.str).join(" ");
    pages.push(pageText);
  }
  return pages.join("\n\n");
}

export const processFile = async (file) => {
  try {
    const fileType = file.type?.toLowerCase() || "";
    let text = "";

    if (fileType === "application/pdf" || file.name?.toLowerCase().endsWith(".pdf")) {
      text = await extractPdfText(file);
    } else {
      // Fallback: read as plain text (covers txt, md, csv, code, etc.)
      text = await file.text();
    }

    return {
      success: true,
      content: text,
      error: null,
    };
  } catch (error) {
    console.error("Error processing document:", error);
    return {
      success: false,
      content: null,
      error: error.message || "Failed to process document",
    };
  }
};

export const processPdfDocument = processFile;
export const processExcelDocument = processFile;
export const processDocxDocument = processFile;
