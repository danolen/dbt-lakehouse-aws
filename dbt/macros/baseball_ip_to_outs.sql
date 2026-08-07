{% macro baseball_ip_to_outs(expr) -%}
{# Convert baseball IP (e.g. 35.2 = 35 + 2/3) to total outs. #}
cast(
    floor({{ expr }}) * 3
    + round(({{ expr }} - floor({{ expr }})) * 10)
    as bigint
)
{%- endmacro %}
