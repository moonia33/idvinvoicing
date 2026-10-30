from decimal import Decimal

from django.db import models


class TaxRule(models.Model):
    """Metiniai IV mokesčių tarifai (globalūs, redaguojami per admin).

    GPM/VSD/PSD taisyklės keičiasi kasmet – tarifai čia, o ne kode.
    """

    year = models.PositiveSmallIntegerField(unique=True)

    gpm_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.05"),
        help_text="GPM tarifas AP iki gpm_flat_cap (nuo 2025 – 5%)",
    )
    gpm_flat_cap = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("20000"),
        help_text="AP riba, iki kurios taikomas gpm_rate",
    )
    gpm_progressive_cap = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("42500"),
        help_text="AP riba, ties kuria faktinis tarifas pasiekia gpm_top_rate",
    )
    gpm_top_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.20"),
        help_text="GPM tarifas AP virš gpm_progressive_cap",
    )
    fixed_deduction_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.30"),
        help_text="Leidžiami atskaitymai – fiksuotas pajamų procentas",
    )
    social_base_share = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.90"),
        help_text="VSD/PSD bazė – procentas apmokestinamojo pelno",
    )
    vsd_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.1252"))
    vsd_rate_pension = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.1552"),
        help_text="VSD tarifas papildomai kaupiant pensijai",
    )
    psd_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.0698"))
    mma_monthly = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("1038"),
        help_text="Minimali mėnesinė alga – minimali VSD/PSD bazė",
    )
    annual_cap = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("96264"),
        help_text="Maksimali metinė VSD/PSD bazė (43 x VDU)",
    )

    class Meta:
        ordering = ["-year"]

    def __str__(self):
        return f"Mokesčių taisyklės {self.year}"
