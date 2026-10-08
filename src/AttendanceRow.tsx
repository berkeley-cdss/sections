import Button from "react-bootstrap/Button";
import { AttendanceStatus } from "./models";
import type { AttendanceStatusType } from "./models";

type Props = {
  editable: boolean;
  status: AttendanceStatusType | null | undefined;
  onClick?: (status: AttendanceStatusType) => void;
};

const buttonColorMap: { [status in AttendanceStatusType]: string } = {
  present: "success",
  excused: "info",
  absent: "danger",
};

export default function AttendanceRow({ editable, status, onClick }: Props) {
  return (
    <>
      {(Object.entries(AttendanceStatus) as Array<[AttendanceStatusType, string]>).map(
        ([statusOption, text]) => (
          <span key={statusOption}>
            <Button
              size="sm"
              variant={
                status === statusOption
                  ? buttonColorMap[statusOption]
                  : `outline-${buttonColorMap[statusOption]}`
              }
              disabled={!editable && status !== statusOption}
              onClick={() => onClick && onClick(statusOption)}
            >
              {text}
            </Button>{" "}
          </span>
        )
      )}
    </>
  );
}
