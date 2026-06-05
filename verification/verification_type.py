from enum import Enum


class VerificationType(str, Enum):

    TEXT_EXISTS = "text_exists"

    URL_CONTAINS = "url_contains"

    PAGE_TITLE = "page_title"

    ELEMENT_VISIBLE = "element_visible"

    ELEMENT_NOT_VISIBLE = "element_not_visible"