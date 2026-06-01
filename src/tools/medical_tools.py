"""
Medical tools for VinmecBot — laparoscopic appendectomy Q&A at Vinmec.
All data is embedded directly in Python: no external DB, no ML library required.
"""

import re
import time
from src.telemetry.logger import logger
from src.telemetry.tool_metrics import tool_tracker

VINMEC_HOTLINE = "1800 599 920"

# ── Phần 1: Knowledge Base ─────────────────────────────────────────────────
#
# Mỗi entry: canonical key (dùng cho matching) → câu trả lời đầy đủ.
# Key dùng dấu cách để _score_query() có thể tokenize chính xác.

_KB: dict[str, str] = {
    "nhịn ăn": (
        "Trước phẫu thuật cần nhịn ăn ít nhất 6 tiếng và nhịn uống ít nhất 2 tiếng. "
        "Thuốc đang dùng hàng ngày vẫn được uống với ngụm nước nhỏ — hỏi bác sĩ để xác nhận."
    ),
    "xét nghiệm": (
        "Các xét nghiệm bắt buộc trước mổ: công thức máu, đông máu (PT, aPTT), nhóm máu, "
        "X-quang ngực thẳng, siêu âm ổ bụng. Bệnh nhân trên 40 tuổi cần thêm điện tâm đồ (ECG)."
    ),
    "thuốc dừng": (
        "Thuốc phải dừng trước mổ: Aspirin / Clopidogrel dừng 7 ngày, Warfarin dừng 5 ngày, "
        "Metformin dừng ngay ngày phẫu thuật. Tuyệt đối không tự ý dừng bất kỳ thuốc nào "
        "mà chưa có chỉ định của bác sĩ điều trị."
    ),
    "chuẩn bị": (
        "Chuẩn bị trước ngày mổ: tắm bằng xà phòng kháng khuẩn tối hôm trước. "
        "Không trang điểm, không sơn móng tay/chân, không đeo trang sức hay đồng hồ. "
        "Mang theo: CMND/CCCD, thẻ BHYT, phiếu chỉ định phẫu thuật. "
        "Cần có người thân đi kèm và ở lại bệnh viện trong suốt quá trình."
    ),
    "ăn uống sau mổ": (
        "Ngày 1 sau mổ: chỉ uống nước lọc và súp loãng, không ăn đặc. "
        "Ngày 2–3: cháo trắng loãng, súp mềm, tránh đồ cứng và nhiều xơ. "
        "Sau 1 tuần có thể ăn bình thường nếu không đau bụng. "
        "Kiêng rượu bia ít nhất 2 tuần; kiêng đồ ăn cay, chiên xào trong 1 tuần đầu."
    ),
    "vận động": (
        "Đi lại nhẹ nhàng trong phòng sau 6–8 tiếng hậu phẫu — giúp phòng ngừa huyết khối tĩnh mạch. "
        "Không nâng vật nặng hơn 5 kg trong 2 tuần đầu. "
        "Không lái xe trong 48 giờ sau gây mê. "
        "Đi bộ nhẹ được phép sau 2 tuần; thể thao cường độ cao (gym, chạy bộ) sau 4–6 tuần."
    ),
    "vết mổ": (
        "Thay băng mỗi ngày, giữ vết mổ khô và sạch hoàn toàn. "
        "Có thể tắm nhẹ sau 48 giờ nhưng không để nước vào trực tiếp — dùng túi nilon che vết mổ. "
        "Không tự bôi thuốc, kem, dầu lên vết mổ khi chưa có chỉ định. "
        "Mổ nội soi để lại 3 vết nhỏ 0.5–1 cm, sẹo mờ dần sau 3–6 tháng."
    ),
    "tái khám": (
        "Tái khám lần đầu sau 7–10 ngày để cắt chỉ và kiểm tra vết mổ lành. "
        "Mang theo phiếu ra viện và đơn thuốc đang dùng. "
        "Nếu xuất hiện triệu chứng bất thường trước lịch tái khám, đến viện ngay — không chờ."
    ),
    "thời gian mổ": (
        "Phẫu thuật nội soi thường kéo dài 30–60 phút tuỳ tình trạng viêm và độ khó. "
        "Nằm viện sau mổ: 1–2 ngày nếu nội soi thành công, 3–5 ngày nếu phải chuyển mổ mở "
        "do ruột thừa vỡ hoặc dính nhiều."
    ),
    "tắm": (
        "Được tắm nhẹ sau 48 giờ hậu phẫu. "
        "Không ngâm bồn tắm, không xuống hồ bơi hoặc ao hồ trong 2 tuần đầu. "
        "Khi tắm hãy che vết mổ bằng túi nilon và băng dán chống nước để tránh vết mổ bị ướt."
    ),
    "chi phí": (
        "Chi phí phẫu thuật nội soi cắt ruột thừa tại Vinmec: khoảng 15–25 triệu đồng tuỳ gói dịch vụ. "
        "Bảo hiểm y tế (BHYT) chi trả một phần theo tỉ lệ quy định. "
        "Gọi 1800 599 920 để được tư vấn chi phí cụ thể và thủ tục thanh toán BHYT."
    ),
    "gây mê": (
        "Phẫu thuật nội soi dùng gây mê toàn thân. "
        "Sau gây mê có thể buồn nôn, chóng mặt nhẹ trong vài giờ đầu — đây là phản ứng bình thường. "
        "Không lái xe, không vận hành máy móc, không ký văn bản pháp lý trong 24 giờ sau gây mê."
    ),
    "đau sau mổ": (
        "Đau nhẹ đến vừa ở vùng bụng trong 2–3 ngày đầu là hoàn toàn bình thường. "
        "Bác sĩ sẽ kê thuốc giảm đau — uống đúng liều và đúng giờ theo đơn. "
        "Nếu đau tăng dần sau 48 giờ hoặc không giảm sau khi đã uống thuốc, cần đến viện ngay."
    ),
    "thuốc sau mổ": (
        "Uống thuốc theo đúng đơn bác sĩ, đủ liều và đủ số ngày được kê. "
        "Kháng sinh thường dùng 5–7 ngày để phòng nhiễm trùng — không tự ý dừng sớm. "
        "Không tự mua thêm thuốc giảm đau ngoài đơn mà chưa hỏi ý kiến bác sĩ."
    ),
    "biến chứng": (
        "Biến chứng có thể gặp: nhiễm trùng vết mổ, chảy máu trong ổ bụng, tắc ruột sau mổ, "
        "áp-xe tồn dư. Tỉ lệ biến chứng của nội soi thấp hơn đáng kể so với mổ mở. "
        "Phát hiện sớm là chìa khoá — gọi ngay 1800 599 920 nếu có bất kỳ triệu chứng bất thường."
    ),
    "hút thuốc rượu": (
        "Không hút thuốc lá ít nhất 2 tuần trước và 2 tuần sau mổ — nicotine làm chậm lành thương "
        "và tăng nguy cơ nhiễm trùng. "
        "Không uống rượu bia trong 2 tuần sau mổ — ảnh hưởng đến hiệu quả kháng sinh và quá trình lành vết thương."
    ),
    "thể thao": (
        "Đi bộ nhẹ được phép sau 2 tuần khi vết mổ đã kéo da. "
        "Bơi lội, đạp xe, yoga nhẹ: sau 4 tuần. "
        "Chạy bộ, gym, nâng tạ, võ thuật: sau 6 tuần và cần bác sĩ xác nhận tại buổi tái khám."
    ),
    "lái xe": (
        "Không lái xe trong 48 giờ ngay sau gây mê vì phản xạ và khả năng phán đoán còn bị ảnh hưởng. "
        "Thông thường có thể lái xe trở lại sau 1 tuần khi không còn dùng thuốc giảm đau gây buồn ngủ."
    ),
    "đi làm": (
        "Công việc văn phòng (ngồi, làm máy tính): có thể đi làm lại sau 1–2 tuần. "
        "Công việc chân tay, bê vác nặng: cần nghỉ ít nhất 3–4 tuần. "
        "Xin giấy chứng nhận nghỉ việc từ bác sĩ tại buổi tái khám."
    ),
    "sẹo": (
        "Mổ nội soi để lại 3 vết sẹo nhỏ 0.5–1 cm ở vùng rốn và hố chậu phải. "
        "Sẹo đỏ trong 1–2 tháng đầu, dần mờ và phẳng sau 3–6 tháng. "
        "Có thể dùng gel trị sẹo (Contractubex, Dermatix) sau khi vết mổ đã khô hẳn — hỏi bác sĩ."
    ),
    "viêm ruột thừa": (
        "Viêm ruột thừa là tình trạng viêm của ruột thừa — một túi nhỏ nằm ở hố chậu phải. "
        "Triệu chứng điển hình: đau quặn quanh rốn rồi lan xuống hố chậu phải, sốt nhẹ, buồn nôn, chán ăn. "
        "Điều trị dứt điểm là phẫu thuật cắt bỏ ruột thừa — trì hoãn có thể dẫn đến vỡ ruột thừa rất nguy hiểm."
    ),
    "nội soi so với mổ mở": (
        "Nội soi ưu điểm hơn mổ mở: ít đau hơn, nằm viện ngắn hơn (1–2 ngày thay vì 3–5), "
        "hồi phục nhanh hơn, ít sẹo hơn, nguy cơ nhiễm trùng thấp hơn. "
        "Mổ mở dùng khi ruột thừa đã vỡ, ổ bụng nhiễm trùng nặng, hoặc cơ sở vật chất không đủ nội soi."
    ),
    "trẻ em": (
        "Phẫu thuật nội soi an toàn cho trẻ từ 3 tuổi trở lên tại Vinmec. "
        "Trẻ em hồi phục nhanh hơn người lớn, thường xuất viện sau 1–2 ngày. "
        "Phụ huynh được ở lại bệnh viện suốt quá trình điều trị."
    ),
    "mang thai": (
        "Phụ nữ mang thai mắc viêm ruột thừa cần can thiệp phẫu thuật khẩn cấp. "
        "Nội soi an toàn trong tam cá nguyệt thứ nhất và thứ hai. "
        "Cần hội chẩn liên khoa ngoại–sản trước khi quyết định phẫu thuật."
    ),
    "táo bón sau mổ": (
        "Táo bón sau mổ rất phổ biến do tác dụng của gây mê và thuốc giảm đau. "
        "Biện pháp: uống đủ 2 lít nước mỗi ngày, đi lại nhẹ sớm, ăn thêm rau mềm từ ngày thứ 3. "
        "Nếu không đi tiêu sau 3 ngày, hỏi bác sĩ về thuốc nhuận tràng nhẹ."
    ),
}

# ── Phần 2: Alias Dictionary ───────────────────────────────────────────────
#
# Map: cụm từ trong query → canonical KB key.
# Dùng khi người dùng dùng cách diễn đạt khác với key trong _KB.

_ALIASES: dict[str, str] = {
    # nhịn ăn
    "không ăn":          "nhịn ăn",
    "nhịn uống":         "nhịn ăn",
    "ăn gì trước":       "nhịn ăn",
    "không được ăn":     "nhịn ăn",
    "bao lâu trước mổ":  "nhịn ăn",
    "trước khi mổ ăn":   "nhịn ăn",
    # ăn uống sau mổ
    "ăn gì":             "ăn uống sau mổ",
    "ăn gì sau":         "ăn uống sau mổ",
    "chế độ ăn":         "ăn uống sau mổ",
    "kiêng ăn":          "ăn uống sau mổ",
    "uống gì":           "ăn uống sau mổ",
    "ăn được gì":        "ăn uống sau mổ",
    "không được ăn gì":  "ăn uống sau mổ",
    # vận động
    "đi lại":            "vận động",
    "nâng vật":          "vận động",
    "hoạt động":         "vận động",
    "được làm gì":       "vận động",
    # tắm
    "tắm được chưa":     "tắm",
    "khi nào tắm":       "tắm",
    "bao giờ tắm":       "tắm",
    # vết mổ
    "chăm sóc vết":      "vết mổ",
    "băng vết":          "vết mổ",
    "thay băng":         "vết mổ",
    "vết thương":        "vết mổ",
    # đau sau mổ
    "bị đau":            "đau sau mổ",
    "đau bụng":          "đau sau mổ",
    "giảm đau":          "đau sau mổ",
    "còn đau":           "đau sau mổ",
    # thuốc sau mổ
    "uống thuốc":        "thuốc sau mổ",
    "kháng sinh":        "thuốc sau mổ",
    "đơn thuốc":         "thuốc sau mổ",
    # gây mê
    "tỉnh gây mê":       "gây mê",
    "sau gây mê":        "gây mê",
    "tác dụng gây mê":   "gây mê",
    # lái xe
    "lái xe được chưa":  "lái xe",
    "lái xe lại":        "lái xe",
    # đi làm
    "đi làm lại":        "đi làm",
    "nghỉ bao lâu":      "đi làm",
    "khi nào đi làm":    "đi làm",
    # thể thao
    "tập thể dục":       "thể thao",
    "chạy bộ":           "thể thao",
    "bơi lội":           "thể thao",
    "tập gym":           "thể thao",
    # chi phí
    "giá bao nhiêu":     "chi phí",
    "tốn bao nhiêu":     "chi phí",
    "bảo hiểm":          "chi phí",
    "thanh toán":        "chi phí",
    # sẹo
    "để lại sẹo":        "sẹo",
    "sẹo to không":      "sẹo",
    "sẹo xấu không":     "sẹo",
    # tái khám
    "cắt chỉ":           "tái khám",
    "khám lại":          "tái khám",
    "hẹn tái khám":      "tái khám",
    # táo bón
    "không đi vệ sinh":  "táo bón sau mổ",
    "không đi tiêu":     "táo bón sau mổ",
    "khó đi tiêu":       "táo bón sau mổ",
}

# ── Phần 3: Danger Signs ───────────────────────────────────────────────────
#
# Map: từ khóa triệu chứng → (mức độ, lời khuyên).
# Mức độ: KHẨN CẤP (3) > NGUY HIỂM (2) > CHÚ Ý (1).
# check_danger_signs() sẽ tìm TẤT CẢ matches và sắp xếp theo mức độ giảm dần.

_SEVERITY_ORDER: dict[str, int] = {
    "KHẨN CẤP":  3,
    "NGUY HIỂM": 2,
    "CHÚ Ý":     1,
}

_DANGER: dict[str, tuple[str, str]] = {
    "khó thở":      ("KHẨN CẤP",  "Khó thở sau phẫu thuật có thể là thuyên tắc phổi — nguy hiểm tính mạng."),
    "đau ngực":     ("KHẨN CẤP",  "Đau ngực sau mổ cần đánh giá khẩn cấp ngay lập tức."),
    "chảy máu nhiều": ("KHẨN CẤP","Chảy máu nhiều từ vết mổ là cấp cứu ngoại khoa — cần xử lý ngay."),
    "bất tỉnh":     ("KHẨN CẤP",  "Mất ý thức sau mổ là tình trạng cấp cứu."),
    "chảy mủ":      ("NGUY HIỂM", "Vết mổ chảy mủ là dấu hiệu nhiễm trùng sâu — cần xử lý y tế trong ngày."),
    "đỏ sưng":      ("NGUY HIỂM", "Vết mổ đỏ, sưng, nóng là dấu hiệu viêm nhiễm tại chỗ."),
    "vết mổ hở":    ("NGUY HIỂM", "Vết mổ bị hở hoặc bung chỉ cần được khâu lại ngay, tránh nhiễm trùng sâu."),
    "sốt cao":      ("NGUY HIỂM", "Sốt trên 38.5°C sau mổ thường chỉ điểm tình trạng nhiễm trùng."),
    "đau tăng":     ("NGUY HIỂM", "Đau bụng tăng dần sau 48 giờ hậu phẫu có thể là biến chứng trong ổ bụng."),
    "bụng cứng":    ("NGUY HIỂM", "Bụng cứng như gỗ sau mổ có thể là dấu hiệu viêm phúc mạc."),
    "vàng da":      ("NGUY HIỂM", "Vàng da sau mổ có thể liên quan đến tổn thương đường mật hoặc gan."),
    "không đi tiểu": ("NGUY HIỂM","Không đi tiểu trong 8 tiếng sau mổ cần báo y tá ngay — có thể bí tiểu do gây mê."),
    "nôn nhiều":    ("CHÚ Ý",     "Nôn kéo dài trên 24 giờ sau mổ — cần liên hệ bác sĩ để được tư vấn."),
    "sốt nhẹ":      ("CHÚ Ý",     "Sốt nhẹ dưới 38°C trong 1–2 ngày đầu thường là phản ứng bình thường, theo dõi thêm."),
    "sốt":          ("CHÚ Ý",     "Sốt sau mổ cần theo dõi — đo nhiệt độ mỗi 4 tiếng và báo ngay nếu vượt 38.5°C."),
    "chóng mặt":    ("CHÚ Ý",     "Chóng mặt kéo dài sau mổ có thể do thiếu nước hoặc phản ứng thuốc — uống nước và nằm nghỉ."),
    "táo bón":      ("CHÚ Ý",     "Táo bón sau mổ phổ biến do gây mê — uống đủ nước, đi lại nhẹ, hỏi bác sĩ nếu không cải thiện sau 3 ngày."),
}

# ── Phần 4: Checklist ─────────────────────────────────────────────────────

_CHECKLIST: dict[str, str] = {
    "pre_surgery": (
        "CHECKLIST TRƯỚC PHẪU THUẬT — Vinmec\n"
        "─────────────────────────────────────\n"
        "□ Nhịn ăn ít nhất 6 tiếng trước giờ vào phòng mổ\n"
        "□ Nhịn uống ít nhất 2 tiếng (kể cả nước lọc)\n"
        "□ Hoàn thành toàn bộ xét nghiệm theo chỉ định bác sĩ\n"
        "□ Dừng thuốc loãng máu đúng số ngày theo hướng dẫn\n"
        "□ Tắm xà phòng kháng khuẩn tối hôm trước ngày mổ\n"
        "□ Không trang điểm, không sơn móng tay/chân\n"
        "□ Tháo tất cả trang sức, đồng hồ, kính áp tròng\n"
        "□ Chuẩn bị: CMND/CCCD + thẻ BHYT + phiếu chỉ định\n"
        "□ Có người thân đi kèm và ở lại bệnh viện\n"
        "□ Thông báo bác sĩ nếu: đang có kinh, dị ứng thuốc, hoặc có bệnh nền"
    ),
    "post_surgery": (
        "CHECKLIST SAU PHẪU THUẬT — Vinmec\n"
        "────────────────────────────────────\n"
        "□ Ngày 1: chỉ uống nước lọc và súp loãng, không ăn đặc\n"
        "□ Đi lại nhẹ nhàng trong phòng sau 6–8 tiếng để phòng huyết khối\n"
        "□ Thay băng vết mổ mỗi ngày, giữ vết mổ khô và sạch\n"
        "□ Uống thuốc đúng giờ, đủ ngày theo đơn (đặc biệt kháng sinh)\n"
        "□ Không nâng vật nặng hơn 5 kg trong 2 tuần đầu\n"
        "□ Không lái xe trong 48 giờ sau gây mê\n"
        "□ Không uống rượu bia trong 2 tuần\n"
        "□ Tái khám sau 7–10 ngày để cắt chỉ và kiểm tra vết mổ\n"
        f"□ Gọi ngay {VINMEC_HOTLINE} nếu: sốt cao, vết mổ đỏ/sưng/mủ, đau tăng, khó thở"
    ),
}

# Aliases cho stage input của get_checklist()
_STAGE_ALIASES: dict[str, str] = {
    "pre":        "pre_surgery",
    "trước mổ":   "pre_surgery",
    "truoc mo":   "pre_surgery",
    "before":     "pre_surgery",
    "chuẩn bị":   "pre_surgery",
    "post":       "post_surgery",
    "sau mổ":     "post_surgery",
    "sau mo":     "post_surgery",
    "after":      "post_surgery",
    "hậu phẫu":   "post_surgery",
}

# ── Phần 5: Search Helpers ─────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Tách văn bản thành tập token (loại bỏ stop words ngắn)."""
    _STOP = {"là", "và", "có", "của", "cho", "với", "trong", "tôi", "bạn",
             "cần", "được", "hay", "khi", "nào", "thì", "bị", "rất", "một"}
    tokens = set(re.findall(r'\w+', text.lower()))
    return tokens - _STOP


def _score_match(query_tokens: set[str], key: str) -> float:
    """
    Tính điểm khớp giữa query và một KB key.
    Score chính = số token khớp.
    Tiebreaker = tỉ lệ key được bao phủ (specificity): ưu tiên key ngắn, khớp hoàn toàn hơn
    key dài chỉ khớp một phần — tránh false positive khi token phổ biến như "sau", "mổ".
    """
    key_tokens = _tokenize(key)
    matched = len(query_tokens & key_tokens)
    if matched == 0 or not key_tokens:
        return 0.0
    specificity = matched / len(key_tokens)   # 1.0 nếu toàn bộ key token khớp
    return matched + specificity * 0.5


def _find_alias_keys(query: str) -> set[str]:
    """Trả về tập canonical KB keys được gợi ý bởi alias dictionary."""
    q = query.lower()
    return {canonical for phrase, canonical in _ALIASES.items() if phrase in q}


def _keyword_matches_symptoms(keyword: str, text: str) -> bool:
    """
    Kiểm tra một danger keyword có trong text không.
    - 1 từ  : exact substring ("sốt" in text).
    - ≥2 từ : TẤT CẢ các từ phải có trong text (thứ tự tự do).
              "đỏ sưng" khớp với cả "đỏ và sưng" lẫn "sưng đỏ tấy".
    Lý do: bệnh nhân thường thêm liên từ ("và", "bị") giữa các từ triệu chứng.
    """
    words = keyword.split()
    if len(words) == 1:
        return keyword in text
    return all(w in text for w in words)

# ── Phần 6: Tool Functions ────────────────────────────────────────────────


def lookup_surgery_info(query: str) -> str:
    """
    Tra cứu thông tin y tế về phẫu thuật cắt ruột thừa nội soi tại Vinmec.
    Input: câu hỏi hoặc từ khóa bất kỳ (string).
    """
    t0 = time.perf_counter()
    query_tokens = _tokenize(query)
    alias_keys = _find_alias_keys(query)

    # Tính score cho từng KB entry
    scored: list[tuple[int, str, str]] = []
    for key, info in _KB.items():
        base  = _score_match(query_tokens, key)
        bonus = 2 if key in alias_keys else 0
        total = base + bonus
        if total > 0:
            scored.append((total, key, info))

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    alias_used = bool(alias_keys)

    if not scored:
        logger.log_event("TOOL_NO_MATCH", {
            "tool":       "lookup_surgery_info",
            "query":      query,
            "elapsed_ms": elapsed_ms,
        })
        tool_tracker.record("lookup_surgery_info", matched=False,
                            elapsed_ms=elapsed_ms, alias_used=alias_used)
        return (
            f"Xin lỗi, chưa có thông tin cụ thể cho câu hỏi này. "
            f"Vui lòng liên hệ bác sĩ Vinmec: {VINMEC_HOTLINE}."
        )

    scored.sort(key=lambda x: -x[0])
    top = scored[:2]  # Tối đa 2 kết quả để tránh over-inform
    matched_keys = [k for _, k, _ in top]

    logger.log_event("TOOL_EXECUTED", {
        "tool":         "lookup_surgery_info",
        "query":        query,
        "matched_keys": matched_keys,
        "top_score":    top[0][0],
        "candidates":   len(scored),
        "elapsed_ms":   elapsed_ms,
    })
    tool_tracker.record("lookup_surgery_info", matched=True,
                        elapsed_ms=elapsed_ms, score=top[0][0], alias_used=alias_used)

    return "\n\n".join(info for _, _, info in top)


def check_danger_signs(symptoms: str) -> str:
    """
    Đánh giá mức độ nguy hiểm của triệu chứng sau phẫu thuật.
    Input: mô tả triệu chứng bệnh nhân đang gặp (string).
    Trả về tất cả danger signs tìm thấy, sắp xếp theo mức độ nghiêm trọng giảm dần.
    """
    t0 = time.perf_counter()
    s = symptoms.lower()

    matches: list[tuple[int, str, str, str]] = []
    for keyword, (level, advice) in _DANGER.items():
        if _keyword_matches_symptoms(keyword, s):
            matches.append((_SEVERITY_ORDER[level], keyword, level, advice))

    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    if not matches:
        logger.log_event("TOOL_EXECUTED", {
            "tool":       "check_danger_signs",
            "symptoms":   symptoms,
            "matched":    [],
            "elapsed_ms": elapsed_ms,
        })
        tool_tracker.record("check_danger_signs", matched=False, elapsed_ms=elapsed_ms)
        return (
            "Triệu chứng bạn mô tả không nằm trong danh sách cảnh báo khẩn. "
            f"Nếu lo lắng hoặc có triệu chứng bất thường khác, gọi Vinmec: {VINMEC_HOTLINE}."
        )

    # Sắp xếp theo mức độ giảm dần; cùng mức thì theo thứ tự alphabet (ổn định)
    matches.sort(key=lambda x: (-x[0], x[1]))
    max_severity = matches[0][0]

    logger.log_event("TOOL_EXECUTED", {
        "tool":             "check_danger_signs",
        "symptoms":         symptoms,
        "matched":          [{"keyword": kw, "level": lv} for _, kw, lv, _ in matches],
        "highest_severity": matches[0][2],
        "elapsed_ms":       elapsed_ms,
    })
    tool_tracker.record("check_danger_signs", matched=True, elapsed_ms=elapsed_ms)

    lines = [f"[{level}] {advice}" for _, _, level, advice in matches]
    response = "\n".join(lines)

    # Thêm hotline khi có ít nhất một dấu hiệu NGUY HIỂM hoặc KHẨN CẤP
    if max_severity >= _SEVERITY_ORDER["NGUY HIỂM"]:
        response += f"\n\n⚠️  Đến cơ sở y tế ngay hoặc gọi Vinmec: {VINMEC_HOTLINE} (miễn phí, 24/7)."

    return response


def get_checklist(stage: str) -> str:
    """
    Lấy checklist việc cần làm theo giai đoạn phẫu thuật.
    Input: 'pre_surgery' (trước mổ) hoặc 'post_surgery' (sau mổ).
    """
    t0 = time.perf_counter()
    # Alias lookup trước khi replace(" ", "_") để "sau mổ" / "trước mổ" resolve đúng
    raw_key      = stage.lower().strip()
    resolved_key = _STAGE_ALIASES.get(raw_key, raw_key)
    alias_used   = resolved_key != raw_key
    key          = resolved_key.replace(" ", "_")

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    result = _CHECKLIST.get(key)

    if result:
        logger.log_event("TOOL_EXECUTED", {
            "tool":           "get_checklist",
            "stage_input":    stage,
            "stage_resolved": key,
            "alias_used":     alias_used,
            "elapsed_ms":     elapsed_ms,
        })
        tool_tracker.record("get_checklist", matched=True,
                            elapsed_ms=elapsed_ms, alias_used=alias_used)
        return result

    logger.log_event("TOOL_NO_MATCH", {
        "tool":        "get_checklist",
        "stage_input": stage,
        "elapsed_ms":  elapsed_ms,
    })
    tool_tracker.record("get_checklist", matched=False,
                        elapsed_ms=elapsed_ms, alias_used=alias_used)
    return (
        "Vui lòng nhập giai đoạn hợp lệ:\n"
        "• 'pre_surgery'  — checklist chuẩn bị trước phẫu thuật\n"
        "• 'post_surgery' — checklist chăm sóc sau phẫu thuật"
    )


# ── Phần 7: Tool Registry ──────────────────────────────────────────────────
#
# TOOLS là danh sách dict mà ReActAgent đọc để biết tên, mô tả, và hàm thực thi.
# Description phải đủ cụ thể để LLM chọn đúng tool và KHÔNG dùng nhầm.

TOOLS: list[dict] = [
    {
        "name": "lookup_surgery_info",
        "description": (
            "Tra cứu thông tin y tế về phẫu thuật cắt ruột thừa nội soi tại Vinmec. "
            "Dùng cho câu hỏi về: chuẩn bị trước mổ, nhịn ăn, xét nghiệm, thuốc dừng, "
            "chế độ ăn sau mổ, tắm rửa, vết mổ, tái khám, thời gian mổ, gây mê, "
            "đi làm, thể thao, lái xe, chi phí, sẹo. "
            "KHÔNG dùng khi bệnh nhân đang mô tả triệu chứng bất thường sau mổ — dùng check_danger_signs. "
            "KHÔNG dùng khi bệnh nhân hỏi checklist đầy đủ — dùng get_checklist. "
            'Ví dụ: lookup_surgery_info("nhịn ăn bao lâu trước mổ")'
        ),
        "function": lookup_surgery_info,
    },
    {
        "name": "check_danger_signs",
        "description": (
            "Đánh giá mức độ nguy hiểm của triệu chứng bệnh nhân đang gặp sau phẫu thuật. "
            "Dùng khi bệnh nhân mô tả triệu chứng hiện tại: sốt, đau tăng, khó thở, "
            "vết mổ đỏ/sưng/chảy mủ, nôn nhiều, không tiểu được, chóng mặt, v.v. "
            "Trả về mức độ KHẨN CẤP / NGUY HIỂM / CHÚ Ý kèm lời khuyên xử lý cụ thể. "
            'Ví dụ: check_danger_signs("sốt 39 độ, vết mổ bị đỏ và sưng")'
        ),
        "function": check_danger_signs,
    },
    {
        "name": "get_checklist",
        "description": (
            "Lấy checklist đầy đủ việc cần làm theo giai đoạn phẫu thuật. "
            "Dùng khi bệnh nhân hỏi 'cần chuẩn bị gì trước mổ', 'cần làm gì sau mổ', "
            "hoặc yêu cầu danh sách / checklist tổng hợp. "
            "Input bắt buộc: 'pre_surgery' (trước mổ) hoặc 'post_surgery' (sau mổ). "
            'Ví dụ: get_checklist("post_surgery")'
        ),
        "function": get_checklist,
    },
]
