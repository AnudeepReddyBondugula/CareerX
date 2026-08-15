from pathlib import Path

from careerx.renderers.resume_renderer import ResumeRenderer
from careerx.services.profile_service import ProfileService
from careerx.utils import PDFGenerator

profile_service = ProfileService()

resume = profile_service.load_profile()

renderer = ResumeRenderer(
    template_dir=Path("src/careerx/templates"),
)

renderer.render(
    resume=resume,
    output_path=Path("output/treyHunner.tex"),
    template_name="treyHunner.tex.j2",
)


generator = PDFGenerator()

pdf_path = generator.generate(
    tex_file=Path("output/treyHunner.tex"),
    output_dir=Path("output"),
)

print(pdf_path)
