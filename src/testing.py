from pathlib import Path

from careerx.renderers.resume_renderer import ResumeRenderer
from careerx.services.profile_service import ProfileService

profile_service = ProfileService()

resume = profile_service.load_profile()

renderer = ResumeRenderer(
    template_dir=Path("src/careerx/templates"),
)

renderer.render(
    resume=resume,
    output_path=Path("output/resume.tex"),
)


from pathlib import Path

from careerx.utils import PDFGenerator

generator = PDFGenerator()

pdf_path = generator.generate(
    tex_file=Path("output/resume.tex"),
    output_dir=Path("output"),
)

print(pdf_path)