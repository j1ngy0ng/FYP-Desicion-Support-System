# Human-participant ethics gate

The prototype does not enable participant recruitment by default. The human-study endpoints remain locked unless the environment variable `ETHICS_APPROVAL_REFERENCE` contains the formal TAR UMT ethics approval or exemption reference.

Before enabling the study:

1. Submit the approved protocol, participant information sheet, consent form, recruitment material and instruments to the responsible TAR UMT authority.
2. Obtain the formal approval or exemption letter/email.
3. Store a copy of the approval evidence outside the public source repository if it contains personal or administrative data.
4. Add the reference, approval date and approved scope to Chapter 3 and the relevant appendix.
5. Set `ETHICS_APPROVAL_REFERENCE` only for the approved study deployment.
6. Do not recruit participants or report a completed human study before approval/exemption.

If approval is not obtained, Chapter 5 must describe the human evaluation as proposed future work and must not report participant results.
