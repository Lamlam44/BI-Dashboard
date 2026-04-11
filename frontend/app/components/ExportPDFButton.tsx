'use client';

import { useState, type RefObject } from 'react';
import { FileDown, Loader2 } from 'lucide-react';

const MARGIN = 12;
const HDR_H  = 20;
const A4_H   = 297;
const BODY_H = A4_H - MARGIN - HDR_H - 10;

export interface ExportPDFButtonProps {
  /** Async fn that builds a Blob using @react-pdf/renderer inside the PDF doc file */
  generateBlob?: () => Promise<Blob>;
  /** DOM ref for html2canvas screenshot fallback (Item Trends) */
  contentRef?: RefObject<HTMLElement | null>;
  reportTitle?: string;
  filterInfo?: string;
  filename?: string;
  disabled?: boolean;
  className?: string;
}

export default function ExportPDFButton({
  generateBlob,
  contentRef,
  reportTitle = 'BI Dashboard Report',
  filterInfo,
  filename = 'bi-report',
  disabled = false,
  className = '',
}: ExportPDFButtonProps) {
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    if (exporting) return;
    setExporting(true);
    try {
      if (generateBlob) {
        const blob = await generateBlob();
        _triggerDownload(blob, filename);
      } else if (contentRef?.current) {
        await _exportCapture(contentRef.current, filename, reportTitle, filterInfo);
      }
    } catch (err) {
      console.error('[ExportPDF]', err);
      alert('Xuất PDF thất bại: ' + (err instanceof Error ? err.message : String(err)));
    } finally {
      setExporting(false);
    }
  };

  return (
    <button
      onClick={handleExport}
      disabled={disabled || exporting}
      title="Xuất báo cáo PDF"
      className={`export-btn inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium
        bg-rose-600 text-white hover:bg-rose-700 disabled:opacity-50 disabled:cursor-not-allowed
        transition-colors shadow-sm ${className}`}
    >
      {exporting
        ? <><Loader2 size={15} className="animate-spin" /> Đang xuất...</>
        : <><FileDown size={15} /> Xuất PDF</>}
    </button>
  );
}

async function _exportCapture(
  el: HTMLElement,
  filename: string,
  reportTitle: string,
  filterInfo?: string,
) {
  // Expand all overflow/max-height containers so full data is captured
  const overrides: { node: HTMLElement; prev: string }[] = [];
  el.querySelectorAll<HTMLElement>('[class]').forEach((node) => {
    const cls = node.getAttribute('class') ?? '';
    if (/max-h-|overflow-auto|overflow-y-auto|overflow-hidden/.test(cls)) {
      overrides.push({ node, prev: node.style.cssText });
      node.style.maxHeight = 'none';
      node.style.overflow  = 'visible';
      node.style.height    = 'auto';
    }
  });

  await new Promise((r) => setTimeout(r, 80));

  const [{ jsPDF }, html2canvas] = await Promise.all([
    import('jspdf'),
    import('html2canvas'),
  ]);

  let canvas: HTMLCanvasElement;
  try {
    canvas = await html2canvas.default(el, {
      scale: 2,
      useCORS: true,
      logging: false,
      backgroundColor: '#f8fafc',
      windowWidth:  el.scrollWidth,
      windowHeight: el.scrollHeight,
      ignoreElements: (e) =>
        e.classList.contains('no-pdf') || e.classList.contains('export-btn'),
    });
  } finally {
    overrides.forEach(({ node, prev }) => { node.style.cssText = prev; });
  }

  const pdf  = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
  const pW   = pdf.internal.pageSize.getWidth();
  const pH   = pdf.internal.pageSize.getHeight();
  const imgW = pW - MARGIN * 2;
  const pxPerMM = canvas.width / imgW;
  const slicePx = BODY_H * pxPerMM;
  const now     = new Date().toLocaleString('vi-VN', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });

  let srcY = 0, pageIdx = 0;

  while (srcY < canvas.height) {
    if (pageIdx > 0) pdf.addPage();

    const thisPx = Math.min(slicePx, canvas.height - srcY);
    const thisH  = thisPx / pxPerMM;

    const slice = document.createElement('canvas');
    slice.width  = canvas.width;
    slice.height = thisPx;
    slice.getContext('2d')!.drawImage(
      canvas, 0, srcY, canvas.width, thisPx,
      0, 0, canvas.width, thisPx,
    );

    pdf.setFont('helvetica', 'bold');
    pdf.setFontSize(pageIdx === 0 ? 13 : 10);
    pdf.setTextColor(15, 23, 42);
    pdf.text('BI Dashboard', MARGIN, MARGIN + 5);

    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(pageIdx === 0 ? 10 : 9);
    pdf.setTextColor(71, 85, 105);
    pdf.text(reportTitle, pW - MARGIN, MARGIN + 5, { align: 'right' });

    if (pageIdx === 0 && filterInfo) {
      pdf.setFontSize(8);
      pdf.setTextColor(100, 116, 139);
      pdf.text('Period: ' + filterInfo, MARGIN, MARGIN + 11);
    }
    pdf.setFontSize(8);
    pdf.setTextColor(100, 116, 139);
    pdf.text('Generated: ' + now, pW - MARGIN, MARGIN + 11, { align: 'right' });

    pdf.setDrawColor(59, 130, 246);
    pdf.setLineWidth(0.4);
    pdf.line(MARGIN, MARGIN + HDR_H - 2, pW - MARGIN, MARGIN + HDR_H - 2);

    pdf.addImage(slice.toDataURL('image/png'), 'PNG', MARGIN, MARGIN + HDR_H, imgW, thisH);

    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(7);
    pdf.setTextColor(148, 163, 184);
    pdf.text('Confidential - Internal Use Only', MARGIN, pH - 6);
    pdf.text(`Page ${pageIdx + 1}`, pW - MARGIN, pH - 6, { align: 'right' });

    srcY += thisPx;
    pageIdx++;
  }

  _triggerDownload(pdf.output('blob'), filename);
}

function _triggerDownload(blob: Blob, filename: string) {
  const url   = URL.createObjectURL(blob);
  const a     = document.createElement('a');
  const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  a.href      = url;
  a.download  = `${filename}_${stamp}.pdf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}