"""PDF generation utilities."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFGenerationError(RuntimeError):
    """Raised when PDF generation fails."""


class PDFGenerator:
    """Compile LaTeX into a PDF."""

    LATEX_COMMAND = "pdflatex"

    def generate(
        self,
        *,
        tex_file: Path,
        output_dir: Path,
        clean_auxiliary: bool = True,
    ) -> Path:
        """
        Compile a LaTeX document into a PDF.

        Args:
            tex_file:
                Path to the .tex file.

            output_dir:
                Directory where the PDF should be written.

            clean_auxiliary:
                Remove temporary LaTeX files after compilation.

        Returns:
            Path to generated PDF.

        Raises:
            FileNotFoundError:
                If the .tex file does not exist.

            PDFGenerationError:
                If compilation fails.
        """
        if not tex_file.exists():
            raise FileNotFoundError(f"{tex_file} does not exist.")

        if shutil.which(self.LATEX_COMMAND) is None:
            raise PDFGenerationError(
                "pdflatex was not found. "
                "Please install TeX Live or MiKTeX."
            )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        logger.info("Generating PDF from %s", tex_file)

        command = [
            self.LATEX_COMMAND,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={output_dir}",
            str(tex_file),
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            logger.error(result.stdout)
            logger.error(result.stderr)

            raise PDFGenerationError(
                "LaTeX compilation failed.\n"
                f"{result.stderr}"
            )

        pdf_file = output_dir / f"{tex_file.stem}.pdf"

        if not pdf_file.exists():
            raise PDFGenerationError(
                "PDF compilation completed but output PDF was not found."
            )

        logger.info("PDF generated successfully: %s", pdf_file)

        if clean_auxiliary:
            self._cleanup_auxiliary_files(
                tex_file=tex_file,
                output_dir=output_dir,
            )

        return pdf_file

    @staticmethod
    def _cleanup_auxiliary_files(
        *,
        tex_file: Path,
        output_dir: Path,
    ) -> None:
        """Remove LaTeX auxiliary files."""

        extensions = (
            ".aux",
            ".log",
            ".out",
            ".toc",
            ".fls",
            ".fdb_latexmk",
            ".synctex.gz",
        )

        for extension in extensions:
            file = output_dir / f"{tex_file.stem}{extension}"

            if file.exists():
                file.unlink()