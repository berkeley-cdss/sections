import Tooltip from "react-bootstrap/Tooltip";
import OverlayTrigger from "react-bootstrap/OverlayTrigger";
import { InfoCircle } from "react-bootstrap-icons";

type Props = {
  text: string;
};

export default function InfoTooltip({ text }: Props) {
  return (
    <OverlayTrigger
      placement="right"
      overlay={<Tooltip id="info-tooltip">{text}</Tooltip>}
    >
      <span style={{ marginLeft: "6px", cursor: "pointer" }}>
        <InfoCircle />
      </span>
    </OverlayTrigger>
  );
}
