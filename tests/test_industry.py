from evidence_research.industry import IndustryRequest, build_industry_prompt


def test_industry_prompt_contains_constraints_and_dimensions() -> None:
    prompt = build_industry_prompt(
        IndustryRequest(
            question="What is the competitive landscape?",
            industry="新能源汽车",
            region="中国",
            time_range="2023-2025",
            companies=["比亚迪", "特斯拉"],
        )
    )
    assert "Industry: 新能源汽车" in prompt
    assert "Region: 中国" in prompt
    assert "Companies: 比亚迪, 特斯拉" in prompt
    assert "competitive landscape" in prompt
