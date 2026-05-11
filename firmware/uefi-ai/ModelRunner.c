/**
 * ModelRunner.c - Phase 34 inference stub.
 * Phase 38 will replace this heuristic with GGML Q4 inference.
 */

#include <Uefi.h>

#include <Library/UefiLib.h>

#define KRYOS_DECISION_NORMAL   L"NORMAL"
#define KRYOS_DECISION_REPAIR   L"REPAIR"
#define KRYOS_DECISION_SAFE     L"SAFE"
#define KRYOS_DECISION_RECOVERY L"RECOVERY"

typedef struct {
  UINT32  CpuCount;
  UINT64  RamMb;
  UINT32  DiskCount;
  BOOLEAN DiskSmartErrors;
  CHAR16  GpuVendor[32];
  CHAR16  BootDevice[64];
  CHAR16  UefiVersion[32];
  BOOLEAN SecureBootEnabled;
} KRYOS_HW_PROFILE;

CONST CHAR16 *
KryosInferBootDecision(
  IN CONST KRYOS_HW_PROFILE *Profile
  )
{
  if (Profile == NULL) {
    return KRYOS_DECISION_NORMAL;
  }

  // Phase 34 heuristic policy that mimics tiny quantized classifier behavior.
  if (Profile->DiskSmartErrors) {
    return KRYOS_DECISION_REPAIR;
  }

  if (Profile->RamMb < 2048) {
    return KRYOS_DECISION_SAFE;
  }

  if ((Profile->RamMb >= 4096) && !Profile->DiskSmartErrors) {
    return KRYOS_DECISION_NORMAL;
  }

  return KRYOS_DECISION_NORMAL;
}
