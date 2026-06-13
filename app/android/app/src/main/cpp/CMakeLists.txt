cmake_minimum_required(VERSION 3.22)
project(dilithium_plegma C)

# =============================================================================
# PLEGMA DAG — Native Dilithium3 + BLAKE3 Bridge
# CVE-007 / CVE-008 PATCH: substitui simulação SHA-256 por criptografia real
#
# Dependências (fetched automaticamente pelo Gradle/CMake):
#   - PQClean/dilithium3/clean  — implementação de referência CRYSTALS-Dilithium3
#   - BLAKE3-team/BLAKE3         — hash pós-quântico (paridade com nó Python)
#
# ABI targets: armeabi-v7a, arm64-v8a, x86, x86_64
# =============================================================================

include(FetchContent)

# ----------------------------------------------------------------------------
# PQClean — CRYSTALS-Dilithium3 (implementação limpa, sem SIMD)
# ----------------------------------------------------------------------------
FetchContent_Declare(
    pqclean
    GIT_REPOSITORY https://github.com/PQClean/PQClean.git
    GIT_TAG        master
    GIT_SHALLOW    TRUE
    GIT_SUBMODULES ""
)
FetchContent_MakeAvailable(pqclean)

set(DILITHIUM3_DIR ${pqclean_SOURCE_DIR}/crypto_sign/ml-dsa-65/clean)
set(PQCLEAN_COMMON ${pqclean_SOURCE_DIR}/common)

file(GLOB DILITHIUM3_SOURCES "${DILITHIUM3_DIR}/*.c")

# ----------------------------------------------------------------------------
# BLAKE3 — implementação de referência portável em C
# ----------------------------------------------------------------------------
FetchContent_Declare(
    blake3
    GIT_REPOSITORY https://github.com/BLAKE3-team/BLAKE3.git
    GIT_TAG        1.5.1
    GIT_SHALLOW    TRUE
)
FetchContent_MakeAvailable(blake3)

set(BLAKE3_DIR ${blake3_SOURCE_DIR}/c)

# ----------------------------------------------------------------------------
# Biblioteca compartilhada — carregada pelo Dart via FFI
# ----------------------------------------------------------------------------
add_library(dilithium_plegma SHARED
    dilithium_bridge.c

    # Dilithium3/ML-DSA-65 (PQClean/clean — portável, sem SIMD)
    ${DILITHIUM3_SOURCES}

    # PQClean common — SHAKE256/FIPS 202 + randombytes (dependências do ML-DSA-65)
    ${PQCLEAN_COMMON}/fips202.c
    ${PQCLEAN_COMMON}/randombytes.c

    # BLAKE3 (portable, sem AVX/SSE — NEON adicionado condicionalmente abaixo)
    ${BLAKE3_DIR}/blake3.c
    ${BLAKE3_DIR}/blake3_dispatch.c
    ${BLAKE3_DIR}/blake3_portable.c
)

# NEON só existe em ARM targets; x86/x86_64 usa BLAKE3_NO_NEON
if(ANDROID_ABI STREQUAL "arm64-v8a" OR ANDROID_ABI STREQUAL "armeabi-v7a")
    target_sources(dilithium_plegma PRIVATE ${BLAKE3_DIR}/blake3_neon.c)
else()
    target_compile_definitions(dilithium_plegma PRIVATE BLAKE3_NO_NEON)
endif()

target_include_directories(dilithium_plegma PRIVATE
    ${DILITHIUM3_DIR}
    ${PQCLEAN_COMMON}
    ${BLAKE3_DIR}
)

# Desativa SIMD x86 em todas as ABIs Android
target_compile_definitions(dilithium_plegma PRIVATE
    BLAKE3_NO_SSE2
    BLAKE3_NO_SSE41
    BLAKE3_NO_AVX2
    BLAKE3_NO_AVX512
)

target_compile_options(dilithium_plegma PRIVATE
    -O2
    -fvisibility=hidden
    -Wall
    -Wno-unused-function
)

# Garante que os símbolos exportados ficam visíveis no .so
set_target_properties(dilithium_plegma PROPERTIES
    C_VISIBILITY_PRESET     default
    VISIBILITY_INLINES_HIDDEN OFF
)

find_library(log-lib log)
target_link_libraries(dilithium_plegma ${log-lib})
