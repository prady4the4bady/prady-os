/**
 * EfiVarWriter.c - writes KryosBootDecision EFI variable.
 */

#include <Uefi.h>

#include <Library/BaseMemoryLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/UefiLib.h>

#define KRYOS_BOOT_DECISION_VAR_NAME L"KryosBootDecision"

STATIC EFI_GUID gKryosBootDecisionGuid =
  { 0x12345678, 0x1234, 0x1234, {0x12, 0x34, 0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc} };

EFI_STATUS
KryosWriteBootDecisionVariable(
  IN CONST CHAR16 *Decision
  )
{
  UINTN DataSize;

  if (Decision == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  DataSize = (StrLen(Decision) + 1) * sizeof(CHAR16);

  return gRT->SetVariable(
               KRYOS_BOOT_DECISION_VAR_NAME,
               &gKryosBootDecisionGuid,
               EFI_VARIABLE_NON_VOLATILE |
               EFI_VARIABLE_BOOTSERVICE_ACCESS |
               EFI_VARIABLE_RUNTIME_ACCESS,
               DataSize,
               (VOID *)Decision
               );
}
