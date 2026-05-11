/**
 * Kryos BIOS AI - Phase 34
 * Stage 1 (UEFI pre-OS): hardware scan -> decision inference -> EFI var write.
 */

#include <Uefi.h>

#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/PrintLib.h>
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

EFI_STATUS
KryosScanHardware(
  OUT KRYOS_HW_PROFILE *Profile
  );

CONST CHAR16 *
KryosInferBootDecision(
  IN CONST KRYOS_HW_PROFILE *Profile
  );

EFI_STATUS
KryosWriteBootDecisionVariable(
  IN CONST CHAR16 *Decision
  );

STATIC
BOOLEAN
KryosIsAllowedDecision(
  IN CONST CHAR16 *Decision
  )
{
  if (Decision == NULL) {
    return FALSE;
  }

  return (StrCmp(Decision, KRYOS_DECISION_NORMAL) == 0) ||
         (StrCmp(Decision, KRYOS_DECISION_REPAIR) == 0) ||
         (StrCmp(Decision, KRYOS_DECISION_SAFE) == 0) ||
         (StrCmp(Decision, KRYOS_DECISION_RECOVERY) == 0);
}

EFI_STATUS
EFIAPI
UefiMain(
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS       Status;
  KRYOS_HW_PROFILE Profile;
  CONST CHAR16     *Decision;
  UINT64           StartTicks;
  UINT64           EndTicks;

  ZeroMem(&Profile, sizeof(Profile));

  StartTicks = GetPerformanceCounter();

  Status = KryosScanHardware(&Profile);
  if (EFI_ERROR(Status)) {
    Print(L"Kryos BIOS AI: hardware scan failed (%r), fallback NORMAL\n", Status);
    Decision = KRYOS_DECISION_NORMAL;
  } else {
    Decision = KryosInferBootDecision(&Profile);
  }

  if (!KryosIsAllowedDecision(Decision)) {
    Decision = KRYOS_DECISION_NORMAL;
  }

  Status = KryosWriteBootDecisionVariable(Decision);
  if (EFI_ERROR(Status)) {
    Print(L"Kryos BIOS AI: failed to write KryosBootDecision (%r)\n", Status);
    return Status;
  }

  EndTicks = GetPerformanceCounter();
  Print(L"Kryos BIOS AI: Boot decision = %s\n", Decision);
  Print(L"Kryos BIOS AI: target <3s, elapsed ticks = %Lu\n", EndTicks - StartTicks);

  return EFI_SUCCESS;
}
