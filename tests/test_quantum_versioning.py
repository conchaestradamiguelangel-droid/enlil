"""TEST 01B — firma V1/V2 fail-closed (ENLIL_TEST01B_AUDITORIA_DISENO_V3/V4.md §9)."""
import pytest

from enlil.quantum import sign_decree, verify_decree, is_available


pytestmark = pytest.mark.skipif(not is_available(), reason="oqs no disponible en este entorno")


def test_v1_firma_y_verifica_formato_historico_congelado():
    sig = sign_decree("id1", "query", "synthesis", 1000.0, payload_version=1)
    assert len(sig) > 0
    assert verify_decree("id1", "query", "synthesis", 1000.0, sig, payload_version=1) is True


def test_v2_requiere_status_para_firmar():
    with pytest.raises(ValueError):
        sign_decree("id2", "query", "synthesis", 1000.0, payload_version=2, status=None)


def test_v2_status_invalido_falla_al_firmar():
    with pytest.raises(ValueError):
        sign_decree("id2", "query", "synthesis", 1000.0, payload_version=2, status="bogus")


def test_v2_firma_y_verifica_complete():
    sig = sign_decree("id3", "q", "s", 2000.0, payload_version=2, status="complete")
    assert verify_decree("id3", "q", "s", 2000.0, sig, payload_version=2, status="complete") is True


def test_v2_firma_y_verifica_partial():
    sig = sign_decree("id4", "q", "s", 3000.0, payload_version=2, status="partial")
    assert verify_decree("id4", "q", "s", 3000.0, sig, payload_version=2, status="partial") is True


def test_v2_verificar_con_status_distinto_al_firmado_falla():
    """La firma cubre inequívocamente el status -- una salida parcial
    firmada no puede pasar por completa."""
    sig = sign_decree("id5", "q", "s", 4000.0, payload_version=2, status="partial")
    assert verify_decree("id5", "q", "s", 4000.0, sig, payload_version=2, status="complete") is False


def test_v1_y_v2_producen_payloads_distintos_para_los_mismos_datos():
    sig_v1 = sign_decree("id6", "q", "s", 5000.0, payload_version=1)
    sig_v2 = sign_decree("id6", "q", "s", 5000.0, payload_version=2, status="complete")
    assert sig_v1 != sig_v2
    # una firma v1 no debe verificar como v2 ni viceversa
    assert verify_decree("id6", "q", "s", 5000.0, sig_v1, payload_version=2, status="complete") is False
    assert verify_decree("id6", "q", "s", 5000.0, sig_v2, payload_version=1) is False


def test_verify_version_none_falla_cerrado():
    with pytest.raises(ValueError):
        verify_decree("id7", "q", "s", 6000.0, "cualquier_firma", payload_version=None)


def test_verify_version_desconocida_falla_cerrado():
    with pytest.raises(ValueError):
        verify_decree("id7", "q", "s", 6000.0, "cualquier_firma", payload_version=3)


def test_verify_firma_corrupta_devuelve_false_no_excepcion():
    """Regresión directa -- una ValueError interna de la crypto (base64
    malformado) NUNCA debe escapar como excepción no controlada."""
    assert verify_decree("id8", "q", "s", 7000.0, "no_es_base64_valido_!!!", payload_version=1) is False
